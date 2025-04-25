import logging
import re
from functools import reduce
from itertools import groupby
from pathlib import Path
from re import Pattern

import yaml
from prettytable import PrettyTable

from kfcicli.charms import CharmRepo, LocalCharmRepo
from kfcicli.charms import parse_repos_from_path, parse_repos_from_module
from kfcicli.images import ImageReference, get_tags
from kfcicli.metadata import InputError, get as get_metadata, SourceMetadata
from kfcicli.repository import Client, create_repository_client_from_url, \
    GitCredentials
from kfcicli.utils import WithLogging, safe
from typing import Callable
from kfcicli.kubeflow import KubeflowRepo

BLACK_LIST = ["https://github.com/canonical/mysql-k8s-operator"]

module_logger = logging.getLogger(__name__)

class KubeflowCI(WithLogging):

    def __init__(
        self, repos: list[KubeflowRepo], base_path: Path, credentials: GitCredentials
    ):
        self.repos = repos
        self.base_path = base_path
        self.credentials = credentials


    def to_dict(self):
        return [
            repo.to_dict()
            for repo in self.repos
        ]

    def dump(self, filename: Path | str):
        with open(filename, "w") as fid:
            yaml.dump(self.to_dict(), fid)

    @staticmethod
    def iter_charms(modules: list[Path]):
        for filename in modules:
            for charm in parse_repos_from_module(filename):

                if charm.name == "istio_ingressgateway":
                    charm.name = "istio_gateway"

                if charm.url not in BLACK_LIST:
                    yield charm

    @classmethod
    def from_dict(cls, data: list[dict], base_path: Path, credentials: GitCredentials):

        repos = []

        for item in data:

            url = item["url"]
            branch = item["branch"]

            repo = create_repository_client_from_url(
                credentials, url, base_path=base_path
            )

            charms = [CharmRepo(
                name = charm_data["name"],
                url = url,
                tf_module = Path(charm_data["path"]) / "terraform",
                branch = branch
            ) for charm_data in item["charms"]]


            if any([
                branch in remote_branches
                for remote_branches in repo.remote_branches.values()
            ]):
                repo.switch(branch)
            else:
                module_logger.warning(f"Missing selected branch {branch} in remote of repository {url}")

            # Build LocalCharmRepo and skipping repositories that don't have charms
            charms = [
                local_charm
                for charm in charms
                if (local_charm := safe(
                    lambda : LocalCharmRepo.from_charm_repo(charm, get_metadata(repo.base_path / charm.tf_module.parent))
                )())
            ]

            if len(charms)==0:
                continue

            repos.append(KubeflowRepo(repo, charms))

        return KubeflowCI(repos, base_path, credentials)

    @classmethod
    def read(cls, filename: Path | str, base_path: Path, credentials: GitCredentials):
        with open(filename, "r") as fid:
            data = yaml.safe_load(fid)
        return cls.from_dict(data, base_path, credentials)

    @classmethod
    def from_tf_modules(cls, modules: list[Path], base_path: Path, credentials: GitCredentials):

        repos = []

        for url, group in groupby(cls.iter_charms(modules), lambda x: x.url):
            charms = list(group)

            branches = {charm.branch for charm in charms}
            # Verify consistency of branches
            assert len(branches) == 1

            repo = create_repository_client_from_url(
                credentials, url, base_path=base_path
            )

            branch = branches.pop()

            if any([
                branch in remote_branches
                for remote_branches in repo.remote_branches.values()
            ]):
                repo.switch(branch)
            else:
                module_logger.warning(f"Missing selected branch {branch} in remote of repository {url}")

            # Build LocalCharmRepo and skipping repositories that don't have charms
            charms = [
                local_charm
                for charm in charms
                if (local_charm := safe(
                    lambda : LocalCharmRepo.from_charm_repo(charm, get_metadata(repo.base_path / charm.tf_module.parent))
                )())
            ]

            if len(charms)==0:
                continue

            repos.append(KubeflowRepo(repo, charms))

        return KubeflowCI(repos, base_path, credentials)

    @staticmethod
    def _cut_charm_branch(repo: Client, charm: CharmRepo,
                          juju_tf_version: str | None = None, dry_run: bool = False):
        from kfcicli.terraform import set_variable_field, set_version_field

        set_variable_field(
            "channel", "default",
            f"{charm.branch.removeprefix("track/")}/stable",
            filename=repo.base_path / charm.tf_module / "variables.tf"
        )

        if juju_tf_version:
            set_version_field(
                required_version=None,
                providers_version={"juju": juju_tf_version},
                filename=repo.base_path / charm.tf_module / "versions.tf"
            )

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=f"updating tracks for charm {charm.name}", directory=".",
                push=not dry_run, force=True
            )

    def cut_release(
            self,
            branch_name: str,
            title: str,
            juju_tf_version: str | None = None,
            dry_run: bool = False,
            limit: int | None = None
    ):

        for kubeflow_repo in self.repos[:limit]:

            repo, charms = kubeflow_repo.repository, kubeflow_repo.charms

            self.logger.info(f"Cutting branch for repo {repo.base_path}")

            release_branch = charms[0].branch

            all_branches = set(
                sum(repo.remote_branches.values(), list(repo.branches))
            )

            if not release_branch in all_branches:
                repo.create_branch(release_branch, "main")

            # Cut release branch
            repo.switch(release_branch)
            if not dry_run:
                repo.push()

            hash = repo.current_commit

            with (
                repo\
                    .create_branch(branch_name, repo.current_branch)\
                    .with_branch(branch_name)
                as r
            ):
                for charm in charms:
                    self._cut_charm_branch(r, charm, juju_tf_version, dry_run)

                # Open Update branch
                if (
                    not dry_run and not r.get_pull_request(branch_name) and r.current_commit != hash
                ):
                    self.logger.debug(f"Opening PR for branch {branch_name} with base {release_branch}")
                    r.create_pull_request(release_branch, title=title,
                                          body=f"Cutting new release for branch {release_branch}")

    def canon_run(
            self,
            wrapper_func: Callable[[Client,list[LocalCharmRepo],bool],...],
            branch_name: str,
            title: str,
            body: str,
            dry_run: bool = False
    ):
        for kubeflow_repo in self.repos:

            repo, charms = kubeflow_repo.repository, kubeflow_repo.charms

            current_branch = repo.current_branch
            hash = repo.current_commit

            with (
                repo \
                        .create_branch(branch_name, repo.current_branch) \
                        .with_branch(branch_name)
                as r
            ):
                wrapper_func(r, charms, dry_run)

                if (
                    not dry_run and not r.get_pull_request(branch_name) and r.current_commit != hash
                ):
                    r.create_pull_request(
                        current_branch,
                        title=title,
                        body=body
                    )

    def pull_request(self, branch_name: str):
        from kfcicli.kubeflow import PullRequests

        return PullRequests({
            kubeflow_repo.repository._git_repo.remote().url: pr
            for kubeflow_repo in self.repos
            if (pr := kubeflow_repo.repository.get_pull_request(branch_name))
        })

    def summary_images(self):
        table = PrettyTable()
        table.field_names = ["repo", "charm", "docs", "image", "current_tag", "last_tag"]

        for kubeflow_repo in self.repos:
            repo, charms = kubeflow_repo.repository, kubeflow_repo.charms
            for charm in charms:
                ref = ImageReference.parse(charm.metadata.resources["oci-image"])

                current_tag = ref.tag
                last_tag = sorted(get_tags(ref), key=lambda tag: tag.last_update)[
                    -1]

                table.add_row([
                    repo._git_repo.remote().url,
                    charm.name,
                    charm.metadata.docs or "",
                    f"{ref.namespace}/{ref.name}",
                    current_tag,
                    last_tag.name
                ])

        print(table)

    @staticmethod
    def _replace(filename: Path, old: str, new: str):
        import subprocess

        normalize = lambda string: string.replace(":", "\\:").replace("/",
                                                                      "\\/")

        subprocess.check_output([
            "sed", '-i', f's/{normalize(old)}/{normalize(new)}/g', str(filename)
        ])

    def update_image_tags(
            self,
            branch_name: str,
            title: str,
            tag_regex: Pattern | None = None
    ):

        for kubeflow_repo in self.repos:

            repo, charms = kubeflow_repo.repository, kubeflow_repo.charms

            current_branch = repo.current_branch

            # Auto-inference for the tag_regex on release branches
            release_branch_prefixes = ["track/", "track/ckf-"]
            if not tag_regex and any(
                    [current_branch.startswith(prefix) for prefix in
                     release_branch_prefixes]):
                branch_version = reduce(
                    lambda _branch, prefix: _branch.removeprefix(prefix),
                    release_branch_prefixes, current_branch
                )
                tag_regex = re.compile(fr"{branch_version}.*")

            with repo.create_branch(branch_name).with_branch(branch_name) as r:

                for charm in charms:

                    local_charm_repo = LocalCharmRepo.from_charm_repo(
                        charm,
                        get_metadata(r.base_path / charm.tf_module.parent)
                    )

                    if local_charm_repo.metadata.source != SourceMetadata.METADATA:
                        raise InputError(
                            "Image parsing from formats other than metadata.yaml is not yet supported.")

                    image_name: str = local_charm_repo.metadata.resources[
                        "oci-image"]
                    ref = ImageReference.parse(image_name)

                    filtered_tags = get_tags(ref) if not tag_regex else (
                        [tag for tag in get_tags(ref) if
                         tag_regex.match(tag.name)]
                    )

                    if not filtered_tags:
                        raise InputError("There are no tags matching the regex")

                    last_tag = \
                        sorted(filtered_tags, key=lambda tag: tag.last_update)[
                            -1].name

                    current_tag = ref.tag
                    if current_tag != last_tag:
                        self._replace(local_charm_repo.metadata.file,
                                      image_name,
                                      image_name.replace(current_tag, last_tag))
                        if r.is_dirty():
                            r.update_branch(
                                f"updating tag for charm {charm.name} to {last_tag}",
                                charm.tf_module.parent,
                            )

                r.create_pull_request(current_branch, title=title)
