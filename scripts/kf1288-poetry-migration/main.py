from json import loads
from os import makedirs, umask
from os.path import abspath, dirname, join
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


def add_poetry_installation_before_tox(content: str) -> str:
    updated_lines = []

    for line in content.splitlines():
        updated_lines.append(line)
        for substring_of_interest, is_tox_installed_afterwards in (
            ("- name: Install dependencies", True),
            ("    charmcraft-channel: 3.x/stable", False)
        ):
            number_of_spaces_before_matching_substring = line.find(substring_of_interest)

            if number_of_spaces_before_matching_substring == -1:
                continue

            indentation = " " * number_of_spaces_before_matching_substring

            if is_tox_installed_afterwards:
                lines_replacing_original_line = [
                    indentation + "- name: Install poetry",
                    indentation + "  uses: ./.github/actions/install-poetry",
                    "",
                    indentation + "- name: Install tox"
                ]
            else:
                lines_replacing_original_line = [
                    line,
                    "",
                    indentation + "- name: Install poetry",
                    indentation + "  uses: ./.github/actions/install-poetry",
                ]

            updated_lines.pop()
            updated_lines.extend(lines_replacing_original_line)

    updated_lines.append("")

    return "\n".join(updated_lines)


def migrate_to_poetry(repo: Client, charms: list[LocalCharmRepo], dry_run: bool) -> None:
    logger.info(f"processing repo at '{repo.base_path}'...")

    commit_message = "ci: let tox find poetry as an external dependency"
    try:
        logger.info("\tadding the new GitHub action...")
        new_github_action_path = repo.base_path / ".github" / "actions" / "install-poetry" / "action.yaml"
        makedirs(dirname(new_github_action_path), exist_ok=True)
        copy(PATH_FOR_THIS_SCRIPT_SUBFOLDER / "action.yaml", new_github_action_path)

        logger.info("\tmodifying workflows using tox...")
        for ci_file_path in (repo.base_path / ".github" / "workflows").glob("*.yaml"):
            logger.info(f"\t\tprocessing '{ci_file_path}'...")
            with open(ci_file_path, "r") as file:
                file_content = file.read()
            updated_file_content = add_poetry_installation_before_tox(content=file_content)
            with open(ci_file_path, "w") as file:
                file.write(updated_file_content)

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=commit_message,
                directory=".",
                push=not dry_run,
                force=True
            )

    except Exception as exception:
        logger.error(f"Something went wrong executing commit '{commit_message}'!")
        raise exception

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
    umask(0)

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
