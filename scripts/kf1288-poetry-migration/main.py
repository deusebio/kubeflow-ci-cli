from json import loads
from os import remove
from os.path import abspath, dirname, exists, join
from shutil import copy
from sys import path as sys_path

sys_path.append(abspath(join(dirname(__file__), "../../")))

from kfcicli.main import (
    Client,
    GitCredentials,
    KubeflowCI,
    LocalCharmRepo,
    Path
)
from kfcicli.utils import setup_logging


PATH_FOR_THIS_SCRIPT_SUBFOLDER = Path(__file__).parent
PATH_FOR_GITHUB_CREDENTIALS = "./credentials.json"
PATH_FOR_MODIFIED_REPOSITORIES = Path("/home/ubuntu/canonical/temp")
PATH_FOR_REPOSITORY_LIST = Path("../../presets/kubeflow-repos.yaml")


logger = setup_logging(log_level="INFO", logger_name=__name__)


def migrate_to_poetry(directory: str) -> bool:
    return (
        update_tox_ini(_dir=directory)
        and update_pyproject_toml(_dir=directory)
        and update_lock_file_and_exported_charm_requirements(_dir=directory)
    )


def main() -> None:
    logger.info(f"temporary repository directory: '{PATH_FOR_MODIFIED_REPOSITORIES}'")

    with open(PATH_FOR_GITHUB_CREDENTIALS, "r") as file:
        credentials = GitCredentials(**loads(file.read()))

    client = KubeflowCI.read(
        filename=PATH_FOR_REPOSITORY_LIST,
        base_path=PATH_FOR_MODIFIED_REPOSITORIES,
        credentials=credentials
    )

    client.canon_run(
        wrapper_func=process_repository,
        branch_name="just-a-dry-run",  # TODO
        title="build: migrate to poetry for Python dependency management",
        body="",  # TODO
        dry_run=True
    )


def process_repository(repo: Client, charms: list[LocalCharmRepo], dry_run: bool) -> None:
    logger.info(f"processing repo at '{repo.base_path}'...")

    commit_message = "docs: add instructions for dependency management"
    logger.info(f"\timplementing commit '{commit_message}'")
    contributing_file_path_from_script = PATH_FOR_THIS_SCRIPT_SUBFOLDER / "CONTRIBUTING.md"
    contributing_file_path_in_repo = repo.base_path / "CONTRIBUTING.md"
    if not exists(contributing_file_path_in_repo):
        copy(contributing_file_path_from_script, contributing_file_path_in_repo)
    else:
        with open(contributing_file_path_from_script, "r") as source_file:
            with open(contributing_file_path_in_repo, "wa") as preexisting_target_file:
                preexisting_target_file.write("\n\n")
                preexisting_target_file.write(source_file.read())
    if repo.is_dirty():
        repo.update_branch(commit_msg=commit_message, directory=".", push=not dry_run, force=True)

    commit_message = "ci: update tox installation and checkout actions"
    logger.info(f"\timplementing commit '{commit_message}'")
    for ci_file_path in (repo.base_path / ".github" / "workflows").glob("*.yaml"):
        with open(ci_file_path, "r") as file:
            file_content = file.read()
        updated_file_content = update_tox_installation_and_checkout_actions(content=file_content)
        with open(ci_file_path, "w") as file:
            file.write(updated_file_content)
    if repo.is_dirty():
        repo.update_branch(commit_msg=commit_message, directory=".", push=not dry_run, force=True)

    commit_message = "build: migrate to poetry for dependency management"
    logger.info(f"\timplementing all commits related to '{commit_message}'")
    for charm in charms:
        actual_commit_message = f"{commit_message} in charm '{charm.name}'"
        logger.info(f"\timplementing commit '{actual_commit_message}'")
        charm_folder = (repo.base_path / charm.tf_module).parent
        success = migrate_to_poetry(directory=charm_folder)
        if success and repo.is_dirty():
            repo.update_branch(commit_msg=actual_commit_message, directory=".", push=not dry_run, force=True)
        elif not success:
            logger.error(f"\t\tfailed implementing commit '{actual_commit_message}'")
    actual_commit_message = f"{commit_message} in base project folder"
    logger.info(f"\t\timplementing commit '{actual_commit_message}'")
    base_project_folder = (repo.base_path / charm.tf_module).parent
    success = migrate_to_poetry(directory=base_project_folder)
    if success and repo.is_dirty():
        repo.update_branch(commit_msg=actual_commit_message, directory=".", push=not dry_run, force=True)
    elif not success:
        logger.error(f"\t\tfailed implementing commit '{actual_commit_message}'")


def update_lock_file_and_exported_charm_requirements(_dir: str) -> bool:
    script_name = "update-lock-file-and-export-charm-requirements.sh"
    script_path_in_repo = _dir / script_name

    copy(script_name, script_path_in_repo)

    try:
        subprocess.check_call(
            ["/bin/bash", script_name],
            cwd=_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True

    except subprocess.CalledProcessError:
        return False

    finally:
        os.remove(script_path_in_repo)


def update_pyproject_toml(_dir: str) -> bool:
    raise NotImplementedError


def update_tox_ini(_dir: str) -> bool:
    raise NotImplementedError


def update_tox_installation_and_checkout_actions(content: str) -> str:
    return (
        content
        .replace("actions/checkout@v2", "actions/checkout@v4")
        .replace("actions/checkout@v3", "actions/checkout@v4")
        .replace("pip install tox", "pipx install tox")
    )


if __name__ == "__main__":
    main()
