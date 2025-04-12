
## Download all repos
from kfcicli.charms import parse_repos_from_path, parse_repos_from_module
from kfcicli.repository import Client, create_repository_client_from_url, \
    GitCredentials
from kfcicli.charms import CharmRepo

from itertools import groupby
from pathlib import Path
from kfcicli.repository import GitCredentials

BLACK_LIST=["https://github.com/canonical/mysql-k8s-operator"]

def iter_charms(modules):
    for filename in modules:
        for charm in parse_repos_from_module(filename):
            if charm.url not in BLACK_LIST:
                yield charm

def download_repos(modules: list[Path], base_path: Path, credentials: GitCredentials, input_branch: str | None = None):

    # Remapping and small cleaning
    charms = list(iter_charms(modules))
    for charm in charms:
        if charm.name == "istio_ingressgateway":
            charm.name = "istio_gateway"

    for url, group in groupby(charms, lambda x: x.url):

        charms = list(group)

        branches = {charm.branch for charm in charms}
        # Verify consistency of branches
        assert len(branches)==1

        repo = create_repository_client_from_url(credentials, url,base_path=base_path).switch(input_branch or branches.pop())

        yield repo, charms


## Reload charms from path

def _cut_charm_branch(repo: Client, charm: CharmRepo, juju_tf_version: str | None = None):
    from kfcicli.terraform import set_variable_field, set_version_field

    set_variable_field(
        "channel", "default", charm.branch,
        filename=repo.base_path / charm.tf_module / "variables.tf"
    )

    if juju_tf_version:
        set_version_field(
            required_version=None,
            providers_version={"juju": ">=0.14.0"},
            filename=repo.base_path / charm.tf_module / "versions.tf"
        )

    repo.update_branch(
        commit_msg=f"updating tracks for charm {charm.name}", directory=".", push=True, force=True
    )


def cut_release(
    branch_name: str, modules: list[Path], base_path: Path,
    title: str,
    credentials: GitCredentials, juju_tf_version: str | None = None
):

    for repo, charms in download_repos(modules, base_path, credentials, input_branch="main"):

        release_branch = charms[0].branch

        # Cut release branch
        repo.create_branch(release_branch, "main").switch(release_branch)
        repo.push()

        with (
            repo.create_branch(branch_name, repo.current_branch).with_branch(branch_name) as r
        ):
            for charm in charms:
                _cut_charm_branch(r, charm, juju_tf_version)

            # Open Update branch
            r.create_pull_request(release_branch, title=title, body=f"Cutting new release for branch {release_branch}")


def summary(branch_name: str, modules: list[Path], base_path: Path, credentials: GitCredentials):
    from prettytable import PrettyTable
    from collections import Counter

    table = PrettyTable()

    table.field_names = ["repo", "pr", "success", "failure", "skipped"]

    for repo, _ in download_repos(modules, base_path, credentials):
        pr = repo.get_pull_request(branch_name)

        last_commit = pr.get_commits().reversed[0]

        cnt = Counter([check.conclusion for check in last_commit.get_check_runs()])

        table.add_row([repo._git_repo.remote().url, pr.html_url, cnt.get("success", 0), cnt.get("failure", 0), cnt.get("skipped", 0)])

    print(table)
