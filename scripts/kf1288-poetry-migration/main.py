from json import loads
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


def update_tox_installation_and_checkout_actions(content: str) -> str:
    return (
        content
        .replace("actions/checkout@v2", "actions/checkout@v4")
        .replace("actions/checkout@v3", "actions/checkout@v4")
        .replace("pip install tox", "pipx install tox")
    )


def migrate_to_poetry(repo: Client, charms: list[LocalCharmRepo], dry_run: bool) -> None:
    logger.info(f"processing repo at '{repo.base_path}'...")

    logger.info("\tadding contributing instructions...")
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
        repo.update_branch(
            commit_msg="docs: add instructions for dependency management",
            directory=".",
            push=not dry_run,
            force=True
        )

    logger.info("\tmodifying workflows using tox...")
    for ci_file_path in (repo.base_path / ".github" / "workflows").glob("*.yaml"):
        with open(ci_file_path, "r") as file:
            file_content = file.read()
        updated_file_content = update_tox_installation_and_checkout_actions(content=file_content)
        with open(ci_file_path, "w") as file:
            file.write(updated_file_content)
    if repo.is_dirty():
        repo.update_branch(
            commit_msg="ci: let tox find poetry as an external dependency",
            directory=".",
            push=not dry_run,
            force=True
        )

    raise NotImplementedError
    # for charm in charms:
    #     charm_folder = (repo.base_path / charm.tf_module).parent
    #     copy(CURRENT_FOLDER / "charmcraft.yaml", charm_folder / "charmcraft.yaml" )
    #     if repo.is_dirty():
    #         repo.update_branch(
    #             commit_msg=f"build: ...TODO... for charm {charm.name}",
    #             directory=".",
    #             push=not dry_run,
    #             force=True
    #         )

    #     success = update_deps(CURRENT_FOLDER / "update-deps.sh", charm_folder )
    #     if not success:
    #         logging.warning(f"Failing to update dependencies on charm {charm.name}")
    #     if success and repo.is_dirty():
    #         repo.update_branch(
    #             commit_msg=f"updating deps for charm {charm.name}",
    #             directory=".",
    #             push=not dry_run, force=True
    #         )

    # success = update_deps(CURRENT_FOLDER / "update-deps.sh", repo.base_path)


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
        wrapper_func=migrate_to_poetry,
        branch_name="just-a-dry-run",  # TODO
        title="build: migrate to poetry for Python dependency management",
        body="",  # TODO
        dry_run=True
    )


if __name__ == "__main__":
    main()
