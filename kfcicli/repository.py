# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for handling interactions with git repository."""

import base64
import logging
import os.path
from collections.abc import Sequence
from contextlib import contextmanager
from functools import cached_property
from itertools import chain
from typing import Any, cast

from git import GitCommandError
from git.diff import Diff
from git.repo import Repo
from github import Github
from github.Auth import Token
from github.GithubException import GithubException, UnknownObjectException
from github.InputGitTreeElement import InputGitTreeElement
from github.PullRequest import PullRequest
from github.Repository import Repository

import re
from collections.abc import Iterator
from itertools import takewhile
from pathlib import Path
from typing import NamedTuple
from kfcicli.metadata import InputError

GITHUB_HOSTNAME = "github.com"
ORIGIN_NAME = "origin"
HTTPS_URL_PATTERN = re.compile(rf"^https?:\/\/.*@?{GITHUB_HOSTNAME}\/(.+\/.+?)(.git)?$")

class FileAddedOrModified(NamedTuple):
    """File that was added, mofied or copied copied in a commit.

    Attributes:
        path: The location of the file on disk.
        content: The content of the file.
    """

    path: Path
    content: str


class FileDeleted(NamedTuple):
    """File that was deleted in a commit.

    Attributes:
        path: The location of the file on disk.
    """

    path: Path

class RepositoryClientError(Exception):
    """A problem with git repository client occurred."""

class RepositoryFileNotFoundError(Exception):
    """A problem retrieving a file from a git repository occurred."""

class RepositoryTagNotFoundError(Exception):
    """A problem retrieving a tag from a git repository occurred."""


# Copied will be mapped to added and renamed will be mapped to be a delete and add
FileAction = FileAddedOrModified | FileDeleted
_ADDED_PATTERN = re.compile(r"A\s*(\S*)")
_MODIFIED_PATTERN = re.compile(r"M\s*(\S*)")
_DELETED_PATTERN = re.compile(r"D\s*(\S*)")
_RENAMED_PATTERN = re.compile(r"R\d+\s*(\S*)\s*(\S*)")
_COPIED_PATTERN = re.compile(r"C\d+\s*(\S*)\s*(\S*)")


def parse_git_show(output: str, repository_path: Path) -> Iterator[FileAction]:
    """Parse the output of a git show with --name-status into manageable data.

    Args:
        output: The output of the git show command.
        repository_path: The path to the git repository.

    Yields:
        Information about each of the files that changed in the commit.
    """
    # Processing in reverse up to empty line to detect end of file changes as an empty line.
    # Example git show output:
    #     git show --name-status <commit sha>
    #     commit <commit sha> (HEAD -> <branch name>)
    #     Author: <author>
    #     Date:   <date>

    #         <commit message>

    #     A       add-file.text
    #     M       change-file.text
    #     D       delete-file.txt
    #     R100    renamed-file.text       is-renamed-file.text
    #     C100    to-be-copied-file.text  copied-file.text
    # The copied example is a guess, was not able to get the copied status during testing
    lines = takewhile(bool, reversed(output.splitlines()))
    for line in lines:
        if (modified_match := _MODIFIED_PATTERN.match(line)) is not None:
            path = Path(modified_match.group(1))
            yield FileAddedOrModified(path, (repository_path / path).read_text(encoding="utf-8"))
            continue

        if (added_match := _ADDED_PATTERN.match(line)) is not None:
            path = Path(added_match.group(1))
            yield FileAddedOrModified(path, (repository_path / path).read_text(encoding="utf-8"))
            continue

        if (delete_match := _DELETED_PATTERN.match(line)) is not None:
            path = Path(delete_match.group(1))
            yield FileDeleted(path)
            continue

        if (renamed_match := _RENAMED_PATTERN.match(line)) is not None:
            old_path = Path(renamed_match.group(1))
            path = Path(renamed_match.group(2))
            yield FileDeleted(old_path)
            yield FileAddedOrModified(path, (repository_path / path).read_text(encoding="utf-8"))
            continue

        if (copied_match := _COPIED_PATTERN.match(line)) is not None:
            path = Path(copied_match.group(2))
            yield FileAddedOrModified(path, (repository_path / path).read_text(encoding="utf-8"))
            continue

class DiffSummary(NamedTuple):
    """Class representing the summary of the dirty status of a repository.

    Attrs:
        is_dirty: boolean indicated whether there is any delta
        new: list of files added in the delta
        removed: list of files removed in the delta
        modified: list of files modified in the delta
    """

    is_dirty: bool
    new: frozenset[str]
    removed: frozenset[str]
    modified: frozenset[str]

    @classmethod
    def from_raw_diff(cls, diffs: Sequence[Diff]) -> "DiffSummary":
        """Return a DiffSummary class from a sequence of git.Diff objects.

        Args:
            diffs: list of git.Diff objects representing the delta between two snapshots.

        Returns:
            DiffSummary class
        """
        new_files = {diff.a_path for diff in diffs if diff.new_file and diff.a_path}
        removed_files = {diff.a_path for diff in diffs if diff.deleted_file and diff.a_path}
        modified_files = {
            diff.a_path
            for diff in diffs
            if diff.renamed_file or diff.change_type == "M"
            if diff.a_path
        }

        return DiffSummary(
            is_dirty=len(diffs) > 0,
            new=frozenset(new_files),
            removed=frozenset(removed_files),
            modified=frozenset(modified_files),
        )

    def __add__(self, other: Any) -> "DiffSummary":
        """Add two instances of DiffSummary classes.

        Args:
            other: DiffSummary object to be added

        Raises:
            ValueError: when the other parameter is not a DiffSummary object

        Returns:
            merged DiffSummary class
        """
        if not isinstance(other, DiffSummary):
            raise ValueError("add operation is only implemented for DiffSummary classes")

        return DiffSummary(
            is_dirty=self.is_dirty or other.is_dirty,
            new=frozenset(self.new).union(other.new),
            removed=frozenset(self.removed).union(other.removed),
            modified=frozenset(self.modified).union(other.modified),
        )

    def __str__(self) -> str:
        """Return string representation of the differences.

        Returns:
            string representing the new, modified and removed files
        """
        modified_str = (f"modified: {','.join(self.modified)}",) if len(self.modified) > 0 else ()
        new_str = (f"new: {','.join(self.new)}",) if len(self.new) > 0 else ()
        removed_str = (f"removed: {','.join(self.removed)}",) if len(self.removed) > 0 else ()
        return " // ".join(chain(modified_str, new_str, removed_str))


def _commit_file_to_tree_element(commit_file: FileAction) -> InputGitTreeElement:
    """Convert a file with an action to a tree element.

    Args:
        commit_file: The file action to convert.

    Returns:
        The git tree element.

    Raises:
        NotImplementedError: for unsupported commit file types.
    """
    if isinstance(commit_file, FileAddedOrModified):
        commit_file = cast(FileAddedOrModified, commit_file)
        return InputGitTreeElement(
            path=str(commit_file.path), mode="100644", type="blob", content=commit_file.content
        )
    elif isinstance(commit_file, FileDeleted):
        commit_file = cast(FileDeleted, commit_file)
        return InputGitTreeElement(
            path=str(commit_file.path), mode="100644", type="blob", sha=None
        )
        # Here just in case, should not occur in production
    else:  # pragma: no cover
        raise NotImplementedError(f"unsupported file in commit, {commit_file}")

class Client:  # pylint: disable=too-many-public-methods
    """Wrapper for git/git-server related functionalities.

    Attrs:
        base_path: The root directory of the repository.
        base_charm_path: The directory of the repository where the charm is.
        docs_path: The directory of the repository where the documentation is.
        metadata: Metadata object of the charm
        has_docs_directory: whether the repository has a docs directory
        current_branch: current git branch used in the repository
        current_commit: current commit checkout in the repository
        branches: list of all branches
    """

    def __init__(
        self, repository: Repo, github_repository: Repository, charm_dir: str = ""
    ) -> None:
        """Construct.

        Args:
            repository: Client for interacting with local git repository.
            github_repository: Client for interacting with remote github repository.
            charm_dir: Relative directory where charm files are located.
        """
        self._git_repo = repository
        self._github_repo = github_repository
        # self._charm_dir = charm_dir
        # self._configure_git_user()

    @cached_property
    def base_path(self) -> Path:
        """Return the Path of the repository.

        Returns:
            Path of the repository.
        """
        return Path(self._git_repo.working_tree_dir or self._git_repo.common_dir)

    @property
    def base_charm_path(self) -> Path:
        """Return the Path of the charm in the repository.

        Returns:
            Path of the repository.
        """
        return self.base_path / self._charm_dir


    # @property
    # def metadata(self) -> Metadata:
    #     """Return the Metadata object of the charm."""
    #     return get_metadata(self.base_charm_path)

    @property
    def current_branch(self) -> str:
        """Return the current branch."""
        try:
            return self._git_repo.active_branch.name
        except TypeError:
            tag = next(
                (tag for tag in self._git_repo.tags if tag.commit == self._git_repo.head.commit),
                None,
            )
            if tag:
                return tag.name
            return self.current_commit

    @property
    def current_commit(self) -> str:
        """Return the current branch."""
        return self._git_repo.head.commit.hexsha

    @property
    def branches(self) -> set[str]:
        """Return all local branches."""
        return {branch.name for branch in self._git_repo.heads}

    @contextmanager
    def with_branch(self, branch_name: str) -> Iterator["Client"]:
        """Return a context for operating within the given branch.

        At the end of the 'with' block, the branch is switched back to what it was initially.

        Args:
            branch_name: name of the branch

        Yields:
            Context to operate on the provided branch
        """
        current_branch = self.current_branch

        try:
            yield self.switch(branch_name)
        finally:
            self.switch(current_branch)

    def get_summary(self, directory: str | Path | None) -> DiffSummary:
        """Return a summary of the differences against the most recent commit.

        Args:
            directory: constraint committed changes to a particular folder only. If None, all the
                folders are committed. Default is the documentation folder.

        Returns:
            DiffSummary object representing the summary of the differences.
        """
        directory = str(directory) if directory else "."
        self._git_repo.git.add(directory)

        return DiffSummary.from_raw_diff(
            self._git_repo.index.diff(None)
        ) + DiffSummary.from_raw_diff(self._git_repo.head.commit.diff())

    def is_commit_in_branch(self, commit_sha: str, branch: str | None = None) -> bool:
        """Check if commit exists in a given branch.

        Args:
            commit_sha: SHA of the commit to be searched for
            branch: name of the branch against which the check is done. When None, the current
                branch is used.

        Raises:
            RepositoryClientError: when the commit is not found in the repository

        Returns:
             boolean representing whether the commit exists in the branch
        """
        star_pattern = re.compile(r"^\* ")
        try:
            # This effectively means preventing a shallow repository to not behave correctly.
            # Note that the special depth 2147483647 (or 0x7fffffff, the largest positive number a
            # signed 32-bit integer can contain) means infinite depth.
            # Reference: https://git-scm.com/docs/shallow
            self._git_repo.git.fetch("--depth=2147483647")
            branches_with_commit = {
                star_pattern.sub("", _branch).strip()
                for _branch in self._git_repo.git.branch("--contains", commit_sha).split("\n")
            }
        except GitCommandError as exc:
            if f"no such commit {commit_sha}" in exc.stderr:
                raise RepositoryClientError(f"{commit_sha} not found in git repository.") from exc
            raise RepositoryClientError(f"unknown error {exc}") from exc
        return (branch or self.current_branch) in branches_with_commit

    def pull(self, branch_name: str | None = None) -> None:
        """Pull content from remote for the provided branch.

        Args:
            branch_name: branch to be pulled from the remote
        """
        if branch_name is None:
            self._git_repo.git.pull()
        else:
            with self.with_branch(branch_name) as repo:
                repo.pull()

    def push(self, branch_name: str | None = None, force: bool = False) -> None:
        """Pull content from remote for the provided branch.

        Args:
            branch_name: branch to be pulled from the remote
        """

        push_args = ["-u"]
        if force:
            push_args.append("-f")

        try:
            branch_name = branch_name or self.current_branch
            with self.with_branch(branch_name) as repo:
                push_args.extend([ORIGIN_NAME, repo.current_branch])
                self._git_repo.git.push(*push_args)
        except GitCommandError as exc:
            raise exc  # noqa: DCO053


    def switch(self, branch_name: str) -> "Client":
        """Switch branch for the repository.

        Args:
            branch_name: name of the branch to switch to.

        Returns:
            Repository object with the branch switched.
        """
        is_dirty = self.is_dirty()

        if is_dirty:
            self._git_repo.git.add(".")
            self._git_repo.git.stash()

        try:
            self._git_repo.git.fetch("--all")
            self._git_repo.git.checkout(branch_name, "--")
        finally:
            if is_dirty:
                self._safe_pop_stash(branch_name)
                self._git_repo.git.reset()
        return self

    def _safe_pop_stash(self, branch_name: str) -> None:
        """Pop stashed changes for given branch.

        Args:
            branch_name: name of the branch

        Raises:
            RepositoryClientError: if the pop encounter a critical error.
        """
        try:
            self._git_repo.git.stash("pop")
        except GitCommandError as exc:
            if "CONFLICT" in exc.stdout:
                logging.warning(
                    "There were some conflicts when popping stashes on branch %s. "
                    "Using stashed version.",
                    branch_name,
                )
                self._git_repo.git.checkout("--theirs", str(self.docs_path))
            else:
                raise RepositoryClientError(
                    f"Unexpected error when switching branch to {branch_name}. {exc=!r}"
                ) from exc

    def create_branch(self, branch_name: str, base: str | None = None) -> "Client":
        """Create a new branch.

        Note that this will not switch branch. To create and switch branch, please pipe the two
        operations together:

        repository.create_branch(branch_name).switch(branch_name)

        Args:
            branch_name: name of the branch to be created
            base: branch or tag to be branched from

        Raises:
            RepositoryClientError: if an error occur when creating a new branch

        Returns:
            Repository client object.
        """
        try:
            if branch_name in self.branches:
                self._git_repo.git.branch("-D", branch_name)
            self._git_repo.git.branch(branch_name, base or self.current_branch)
        except GitCommandError as exc:
            raise RepositoryClientError(f"Unexpected error creating new branch. {exc=!r}") from exc

        return self

    def update_branch(
        self,
        commit_msg: str,
        directory: str | Path | None,
        push: bool = True,
        force: bool = False,
    ) -> "Client":
        """Update branch with a new commit.

        Args:
            commit_msg: commit message to be committed to the branch
            push: push new changes to remote branches
            force: when pushing to remove, use force flag
            directory: constraint committed changes to a particular folder only. If None, all the
                folders are committed. Default is the documentation folder.

        Raises:
            RepositoryClientError: if any error are encountered in the update process

        Returns:
            Repository client with the updated branch
        """
        directory = str(directory) if directory else "."

        try:
            # Create the branch if it doesn't exist

            self._git_repo.git.add("-A", directory)
            self._git_repo.git.commit("-m", f"'{commit_msg}'")
            if push:
                self.push(self.current_branch, force)
        except GitCommandError as exc:
            raise RepositoryClientError(
                f"Unexpected error updating branch {self.current_branch}. {exc=!r}"
            ) from exc
        return self

    def is_same_commit(self, tag: str, commit: str) -> bool:
        """Return whether tag and commit coincides.

        Args:
            tag: name of the tag
            commit: sha of the commit

        Returns:
            True if the two pointers coincides, False otherwise.
        """
        if self.tag_exists(tag):
            with self.with_branch(tag) as repo:
                return repo.current_commit == commit
        return False

    def get_pull_request(self, branch_name: str) -> PullRequest | None:
        """Return open pull request matching the provided branch name.

        Args:
            branch_name: branch name to select open pull requests.

        Raises:
            RepositoryClientError: if more than one PR is open with the given branch name

        Returns:
            PullRequest object. If no PR is found, None is returned.
        """
        open_pull = [
            pull
            for pull in self._github_repo.get_pulls(head=branch_name)
            if pull.head.ref == branch_name
        ]
        if len(open_pull) > 1:
            raise RepositoryClientError(
                f"More than one open pull request with branch {branch_name}"
            )
        if not open_pull:
            return None

        return open_pull[0]

    def create_pull_request(
            self, base: str, title: str | None = None,
            body: str | None = None
    ) -> PullRequest:
        """Create pull request for changes in given repository path.

        Args:
            base: tag or branch against to which the PR is opened
            title: title for the pull request
            body: body for the pull request

        Raises:
            InputError: when the repository is not dirty, hence resulting on an empty pull-request

        Returns:
            Pull request object
        """

        title = title or self.current_branch
        body = body or str(self.get_summary(".."))

        self.push()

        try:
            pull_request = self._github_repo.create_pull(
                title=title,
                body=body,
                base=base,
                head=self.current_branch,
            )
        except GithubException as exc:
            raise RepositoryClientError(
                f"Unexpected error creating pull request. {exc=!r}") from exc

        logging.info("Opening new PR with community contribution: %s", pull_request.html_url)

        return pull_request


    def update_pull_request(self, branch: str) -> None:
        """Update and push changes to the given branch.

        Args:
            branch: name of the branch to be updated
        """
        with self.with_branch(branch) as repo:
            if repo.is_dirty():
                repo.pull()
                msg = str(repo.get_summary(self.docs_path))
                logging.info("Summary: %s", msg)
                logging.info("Updating PR with new commit: %s", msg)
                repo.update_branch(msg, directory=self.docs_path)

    def is_dirty(self, branch_name: str | None = None) -> bool:
        """Check if repository path has any changes including new files.

        Args:
            branch_name: name of the branch to be checked against dirtiness

        Returns:
            True if any changes have occurred.
        """
        if branch_name is None:
            return self._git_repo.is_dirty(untracked_files=True)

        with self.with_branch(branch_name) as client:
            return client.is_dirty()

    def tag_exists(self, tag_name: str) -> str | None:
        """Check if a given tag exists.

        Args:
            tag_name: name of the tag to be checked for existence

        Returns:
            hash of the commit the tag refers to.
        """
        self._git_repo.git.fetch("--all", "--tags", "--force")
        tags = [tag.commit for tag in self._git_repo.tags if tag_name == tag.name]
        if not tags:
            return None
        return tags[0].hexsha

    def tag_commit(self, tag_name: str, commit_sha: str) -> None:
        """Tag a commit, if the tag already exists, it is deleted first.

        Args:
            tag_name: The name of the tag.
            commit_sha: The SHA of the commit to tag.

        Raises:
            RepositoryClientError: if there is a problem with communicating with GitHub
        """
        try:
            if self.tag_exists(tag_name):
                logging.info("Removing tag %s", tag_name)
                self._git_repo.git.tag("-d", tag_name)
                self._git_repo.git.push("--delete", "origin", tag_name)

            logging.info("Tagging commit %s with tag %s", commit_sha, tag_name)
            self._git_repo.git.tag(tag_name, commit_sha)
            self._git_repo.git.push("origin", tag_name)

        except GitCommandError as exc:
            logging.error("Tagging commit failed because of %s", exc)
            raise RepositoryClientError(f"Tagging commit failed. {exc=!r}") from exc

    def get_file_content_from_tag(self, path: str, tag_name: str) -> str:
        """Get the content of a file for a specific tag.

        Args:
            path: The path to the file.
            tag_name: The name of the tag.

        Returns:
            The content of the file for the tag.

        Raises:
            RepositoryTagNotFoundError: if the tag could not be found in the repository.
            RepositoryFileNotFoundError: if the file could not be retrieved from GitHub, more than
                one file is returned or a non-file is returned
            RepositoryClientError: if there is a problem with communicating with GitHub
        """
        # Get the tag
        try:
            tag_ref = self._github_repo.get_git_ref(f"tags/{tag_name}")
            # git has 2 types of tags, lightweight and annotated tags:
            # https://git-scm.com/book/en/v2/Git-Basics-Tagging
            if tag_ref.object.type == "commit":
                # lightweight tag, the SHA of the tag is the commit SHA
                commit_sha = tag_ref.object.sha
            else:
                # annotated tag, need to retrieve the commit SHA linked to the tag
                git_tag = self._github_repo.get_git_tag(tag_ref.object.sha)
                commit_sha = git_tag.object.sha
        except UnknownObjectException as exc:
            raise RepositoryTagNotFoundError(
                f"Could not retrieve the tag {tag_name=}. {exc=!r}"
            ) from exc
        except GithubException as exc:
            raise RepositoryClientError(f"Communication with GitHub failed. {exc=!r}") from exc

        # Get the file contents
        try:
            content_file = self._github_repo.get_contents(path, commit_sha)
        except UnknownObjectException as exc:
            raise RepositoryFileNotFoundError(
                f"Could not retrieve the file at {path=} for tag {tag_name}. {exc=!r}"
            ) from exc
        except GithubException as exc:
            raise RepositoryClientError(f"Communication with GitHub failed. {exc=!r}") from exc

        if isinstance(content_file, list):
            raise RepositoryFileNotFoundError(
                f"Path matched more than one file {path=} for tag {tag_name}."
            )

        if content_file.content is None:
            raise RepositoryFileNotFoundError(
                f"Path did not match a file {path=} for tag {tag_name}."
            )

        return base64.b64decode(content_file.content).decode("utf-8")


def _get_repository_name_from_git_url(remote_url: str) -> str:
    """Get repository name from git remote URL.

    Args:
        remote_url: URL of remote repository.
        e.g. https://github.com/canonical/discourse-gatekeeper.git

    Raises:
        InputError: if invalid repository url was given.

    Returns:
        Git repository name. e.g. canonical/discourse-gatekeeper.
    """
    # return remote_url
    matched_repository = HTTPS_URL_PATTERN.match(remote_url)
    if not matched_repository:

        pattern = re.compile(r"git\@([\w,.]*):([\w]*)\/([\w,.,-]*).git")
        try:
            host, org, repo = pattern.match(remote_url).groups()
            url = f"{org}/{repo}"
            print(url)
            return url
        except:
            raise InputError(f"Invalid remote repository url {remote_url=!r}")
    return matched_repository.group(1)


from dataclasses import dataclass

@dataclass
class GitCredentials:
    username: str
    access_token: str


def create_repository_client_from_path(
    credentials: GitCredentials, base_path: Path, charm_dir: str = ""
) -> Client:
    """Create a Github instance to handle communication with Github server.

    Args:
        credentials: Access token that has permissions to open a pull request.
        base_path: Path where local .git resides in.
        charm_dir: Relative directory where the charm files are located.

    Raises:
        InputError: if invalid access token or invalid git remote URL is provided.

    Returns:
        A Github repository instance.
    """
    if not credentials:
        raise InputError(
            f"Invalid 'access_token' input, it must be non-empty, got {credentials=!r}"
        )

    local_repo = Repo(base_path)

    with local_repo.config_writer(config_level="repository") as config_writer:
        config_writer.set_value("user","name", credentials.username)
        config_writer.set_value("user","password", credentials.access_token)

    logging.info("executing in git repository in the directory: %s", local_repo.working_dir)
    github_client = Github(auth=Token(credentials.access_token))
    remote_url = local_repo.remote().url
    repository_fullname = _get_repository_name_from_git_url(remote_url=remote_url)
    remote_repo = github_client.get_repo(repository_fullname)
    return Client(repository=local_repo, github_repository=remote_repo, charm_dir=charm_dir)

def create_repository_client_from_url(
    credentials: GitCredentials, remote_url: str, charm_dir: str = "", base_path: Path = "/tmp/"
) -> Client:
    """Create a Github instance to handle communication with Github server.

    Args:
        credentials: Username Access token that has permissions to open a pull request.
        base_path: Path where local .git resides in.
        charm_dir: Relative directory where the charm files are located.

    Raises:
        InputError: if invalid access token or invalid git remote URL is provided.

    Returns:
        A Github repository instance.
    """
    if not credentials:
        raise InputError(
            f"Invalid 'access_token' input, it must be non-empty, got {credentials=!r}"
        )

    github_client = Github(auth=Token(credentials.access_token))
    repository_fullname = _get_repository_name_from_git_url(remote_url=remote_url)
    remote_repo = github_client.get_repo(repository_fullname)

    full_path = base_path / os.path.basename(repository_fullname)

    if full_path.exists():
        print(f"repository {full_path} already exists")
        local_repo = Repo(full_path)
        if local_repo.remote().url != remote_url:
            raise InputError(
                "mismatch between provide url and remote information."
                f"Provided: {remote_url} Remote: {local_repo.remote().url}"
            )
    else:
        local_repo = Repo.clone_from(remote_url, full_path)

    with local_repo.config_writer(config_level="repository") as config_writer:
        config_writer.set_value("user","name", credentials.username)
        config_writer.set_value("user","password", credentials.access_token)

    return Client(repository=local_repo, github_repository=remote_repo, charm_dir=charm_dir)
