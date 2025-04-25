import logging

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json
import configparser
import jinja2

setup_logging(log_level="INFO")

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

# tmp_folder = "/home/deusebio/tmp/kfcicli"
base_path = Path("/home/deusebio/tmp/test/charm_repos")
repository_file = Path("presets/test.main.yaml")

client = KubeflowCI.read(repository_file, base_path, credentials)

def reformat_tox(filename: Path):
    config = configparser.ConfigParser()

    config.read(filename)
    with open(filename, 'w') as configfile:
        config.write(configfile)


def add_coverage(filename: Path) -> bool:

    config = configparser.ConfigParser()

    config.read(filename)

    if (
            not "testenv:unit" in config.sections() or
            "coverage xml" in config["testenv:unit"]["commands"]
    ):
        return False

    config["testenv:unit"]["commands"] += "\ncoverage xml"

    with open(filename, 'w') as configfile:
        config.write(configfile)

    return True

def _single_repo_tics(repo_name, filename: Path):
    template = Path("./scripts/kf7281/tics-single-repo.yaml.j2")

    env = jinja2.Environment()
    with open(template, "r") as fid:
        template = env.from_string(fid.read())

    with open(filename, "w") as fid:
        fid.write(template.render(
            project_name=repo_name,
            tics_auth_token="${{ secrets.TICSAUTHTOKEN }}"
        ))


def _multi_repo_tics(repo_name, charms: list[LocalCharmRepo], filename: Path):
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
    filename = repo.base_path / ".github" / "workflows" / "tiobe_scan.yml"
    if len(charms)==1:
        _single_repo_tics(repo.base_path.name, filename)
    else:
        _multi_repo_tics(repo.base_path.name, charms, filename)


def main(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):

    charms_with_unit = []

    for charm in charms:
        if not (filename := charm.metadata.file.parent / "tox.ini").exists():
            continue

        reformat_tox(filename)

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=f"Reformatting tox for charm {charm.name}", directory=".",
                push=not dry_run, force=True
            )

        unit_exists = add_coverage(filename)
        if unit_exists:
            charms_with_unit.append(charm)

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=f"Adding coverage for charm {charm.name}", directory=".",
                push=not dry_run, force=True
            )

    create_tics_file(repo, charms_with_unit)

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

client.canon_run(
    wrapper_func=main,
    branch_name="kf-7281-implementing-tics",
    title="[KF-7281] Enabling TIOBE scan",
    body=PR_BODY,
    dry_run=False
)

