import logging
import os

from pathlib import Path
from kfcicli.main import GitCredentials, KubeflowCI, Client
from kfcicli.charms import LocalCharmRepo
from kfcicli.utils import setup_logging, CommentConfigParser as ConfigParser
import json
import jinja2

def reformat_tox(filename: Path):
    """Import and export a tox file to get the formatting right.

    This is a function with side-effects, that modify the underlying file.

    Args:
        filename: Path, name of the file to be re-formatted
    """
    config = ConfigParser()

    config.read(filename)
    with open(filename, 'w') as configfile:
        config.write(configfile)


def add_coverage(filename: Path) -> bool:
    """Adding the coverage XML report when running the tox unit env.

    This is a function with side-effects, that modify the underlying file.

    Args:
        filename: Path, name of the tox.ini file to be amended

    Returns:
        true if the file was modified, false if it didn't have the unit env.
    """

    config = ConfigParser()

    config.read(filename)

    if (
            not "testenv:unit" in config.sections()
    ):
        return False

    if "coverage xml" not in config["testenv:unit"]["commands"]:
        config["testenv:unit"]["commands"] += "\ncoverage xml"

        with open(filename, 'w') as configfile:
            config.write(configfile)

    return True

def _single_repo_tics(repo_name: str, filename: Path):
    """Create TIOBE scan workflow for a single charm repository.

    This is a function with side-effects, that creates or overwrites the underlying file.

    Args:
        repo_name: str, name of the repository / project to be used in TIOBE
        filename: Path, name of the Github Action file
    """

    template = Path("./scripts/kf7281/tics-single-repo.yaml.j2")

    env = jinja2.Environment()
    with open(template, "r") as fid:
        template = env.from_string(fid.read())

    with open(filename, "w") as fid:
        fid.write(template.render(
            project_name=repo_name,
            tics_auth_token="${{ secrets.TICSAUTHTOKEN }}"
        ))


def _multi_repo_tics(repo_name: str, charms: list[LocalCharmRepo], filename: Path):
    """Create TIOBE scan workflow for a multi charm repository.

    This is a function with side-effects, that creates or overwrites the underlying file.

    Args:
        repo_name: str, name of the repository / project to be used in TIOBE
        charms: list[kfcicli.charms.LocalCharmRepo], list of charms to be included in tiobe scanning
        filename: Path, name of the Github Action file
    """
    template = Path("./scripts/kf7281/tics-multi-repo.yaml.j2")

    env = jinja2.Environment()
    with open(template, "r") as fid:
        template = env.from_string(fid.read())

    input_dict = {
        charm.metadata.name: str(charm.tf_module.parent)
        for charm in charms
    }

    with open(filename, "w") as fid:
        fid.write(template.render(
            project_name=repo_name,
            tics_auth_token="${{ secrets.TICSAUTHTOKEN }}",
            charms=input_dict
        ))


def create_tics_file(repo: Client, charms: list[LocalCharmRepo]):
    """Create TIOBE scan workflow for a repository (either single-charm or multi-charm).

    This is a function with side-effects, that creates or overwrites the underlying file.

    Args:
        repo: kfcicli.repository.Client, client instance representing the repository
        charms: list[kfcicli.charms.LocalCharmRepo], list of charms in the repository
    """

    filename = repo.base_path / ".github" / "workflows" / "tiobe_scan.yml"

    # Checking if repo is single charm or multi charm
    # Note that checking that there is only 1 charm is not enough, since there exists
    # repositories with multi-charm structure but only one charm (e.g. argo-operators)
    if len(charms)==1 and str(charms[0].tf_module) == "terraform":
        _single_repo_tics(repo.base_path.name, filename)
    else:
        _multi_repo_tics(repo.base_path.name, charms, filename)


def main(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):
    """Canon-run main function.

    Signature must comply with the requirements of kfcicli.main.KubeflowCI.canon_run
    """

    charms_with_unit = []

    for charm in charms:
        if not (filename := charm.metadata.file.parent / "tox.ini").exists():
            continue

        # reformatting tox.ini file to be machine-generated and handled
        reformat_tox(filename)

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=f"Reformatting tox for charm {charm.name}", directory=".",
                push=not dry_run, force=True
            )

        # coverage.xml generation when running unit tests
        unit_exists = add_coverage(filename)
        if unit_exists:
            charms_with_unit.append(charm)

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=f"Adding coverage for charm {charm.name}", directory=".",
                push=not dry_run, force=True
            )

    # creating tiobe_scan.yaml file
    create_tics_file(repo, charms_with_unit)

    if repo.is_dirty():
        repo.update_branch(
            commit_msg=f"Adding TICS file", directory=".",
            push=not dry_run, force=True
        )


PR_BODY="""
Updating with TIOBE scan, including:
* reformatting tox.ini file to be machine-generated and handled
* coverage.xml generation when running unit tests 
* creating tiobe_scan.yaml file
"""

if __name__ == "__main__":
    import argparse

    home_folder = os.getenv("HOME", "/home/ubuntu")

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument(
        "input", help="Input file to get the list of repos"
    )
    args_parser.add_argument(
        "--log-level", required=False, default="INFO", help="log level to be used"
    )
    args_parser.add_argument(
        "--base-path", required=False, default=f"{home_folder}/.kfcicli/", help="Base path where to store all repositories"
    )
    args_parser.add_argument(
        "--credentials", required=False, default=f"{home_folder}/.kfcicli/credentials.json", help="File holding the credentials for Github"
    )

    args = args_parser.parse_args()

    setup_logging(log_level=args.log_level)

    with open(args.credentials, "r") as fid:
        credentials = GitCredentials(**json.loads(fid.read()))

    base_path = Path(args.base_path)
    repository_file = Path(args.input)

    client = KubeflowCI.read(repository_file, base_path, credentials)

    client.canon_run(
        wrapper_func=main,
        branch_name="kf-7281-implementing-tics",
        title="[KF-7281] Enabling TIOBE scan",
        body=PR_BODY,
        dry_run=False
    )

