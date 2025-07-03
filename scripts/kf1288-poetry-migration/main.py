from configparser import ConfigParser, NoOptionError
from collections import OrderedDict
from json import loads as json_loads
from os import remove
from os.path import abspath, dirname, exists, join
from pathlib import Path
from re import search
from shutil import copy
from subprocess import CalledProcessError, DEVNULL, check_call
from sys import path as sys_path
from typing import Dict, List, Set, Tuple

from tomlkit import dump as toml_dump, load as toml_load, table

sys_path.append(abspath(join(dirname(__file__), "../../")))

from kfcicli.main import (
    Client,
    GitCredentials,
    KubeflowCI,
    LocalCharmRepo,
    Path
)
from kfcicli.utils import setup_logging


PATH_FOR_MODIFIED_CHARMCRAFT_LINES = Path("modified_charmcraft_lines")
PATH_FOR_GITHUB_CREDENTIALS = "./credentials.json"
PATH_FOR_MODIFIED_REPOSITORIES = Path("/home/mattia/Desktop/canonical/temp")
PATH_FOR_PULL_REQUEST_BODY_TEMPLATE = "./pull_request_body_template.md"
PATH_FOR_REPOSITORY_LIST = Path("../../presets/kubeflow-repos.yaml")
PATH_FOR_THIS_SCRIPT_SUBFOLDER = Path(__file__).parent

ENVIRONMENT_NAME_FOR_CHARM = "charm"
ENVIRONMENT_NAME_FOR_UNIT_TESTING = "unit"
ENVIRONMENT_NAME_FOR_UPDATE_REQUIREMENTS = "update-requirements"
REQUIREMENTS_FILE_NAME_BASE = "requirements"


logger = setup_logging(log_level="INFO", logger_name=__name__)


def main() -> None:
    logger.info(f"temporary repository directory: '{PATH_FOR_MODIFIED_REPOSITORIES}'")

    with open(PATH_FOR_GITHUB_CREDENTIALS, "r") as file:
        credentials = GitCredentials(**json_loads(file.read()))

    with open(PATH_FOR_PULL_REQUEST_BODY_TEMPLATE, "r") as file:
        pull_request_body_template = file.read()

    client = KubeflowCI.read(
        filename=PATH_FOR_REPOSITORY_LIST,
        base_path=PATH_FOR_MODIFIED_REPOSITORIES,
        credentials=credentials
    )

    client.canon_run(
        wrapper_func=process_repository,
        branch_name="kf-7526/poetry-migration",
        title="build: migrate to poetry for Python dependency management",
        body=pull_request_body_template,
        dry_run=False
    )


def migrate_to_poetry(directory: Path, project: str, is_it_a_charm: bool) -> bool:
    if is_it_a_charm:
        update_charmcraft(_dir=directory)
    poetry_group_names_to_versioned_requirements = update_tox_ini(
        _dir=directory,
        are_there_subcharms=not is_it_a_charm
    )
    update_pyproject_toml(
        _dir=directory, project_name=project,
        poetry_group_names_to_versioned_requirements=poetry_group_names_to_versioned_requirements
    )
    return update_lock_file_and_exported_charm_requirements(_dir=directory)


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
            with open(contributing_file_path_in_repo, "w") as preexisting_target_file:
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
    project_name = repo.base_path.name
    visited_charm_folders = set()
    for charm in charms:
        actual_commit_message = f"{commit_message} in charm '{charm.name}'"
        logger.info(f"\t\timplementing commit '{actual_commit_message}'")
        charm_folder = (repo.base_path / charm.tf_module).parent
        visited_charm_folders.add(charm_folder)
        success = migrate_to_poetry(directory=charm_folder, project=project_name, is_it_a_charm=True)
        if success and repo.is_dirty():
            repo.update_branch(commit_msg=actual_commit_message, directory=".", push=not dry_run, force=True)
        elif not success:
            logger.error(f"\t\tfailed implementing commit '{actual_commit_message}'")
    base_project_folder = repo.base_path
    if base_project_folder not in visited_charm_folders:
        actual_commit_message = f"{commit_message} in base project folder"
        logger.info(f"\t\timplementing commit '{actual_commit_message}'")
        success = migrate_to_poetry(directory=base_project_folder, project=project_name, is_it_a_charm=False)
        if success and repo.is_dirty():
            repo.update_branch(commit_msg=actual_commit_message, directory=".", push=not dry_run, force=True)
        elif not success:
            logger.error(f"\t\tfailed implementing commit '{actual_commit_message}'")


def read_versioned_requirements_and_remove_files(file_dir: Path, file_name_base: str) -> Tuple[Dict[str, str], Set]:
    requirement_name_regex = "[^a-zA-Z0-9-_]"

    in_file_path = file_dir / f"{file_name_base}.in"
    txt_file = file_dir / f"{file_name_base}.txt"

    requirements_to_version_contraints = {}
    nested_dependency_groups = set()

    if exists(in_file_path):
        unversioned_requirements = set()

        with open(in_file_path, "r") as file:
            content = file.read()
        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("#") and not line.startswith("-r") and line.strip():
                first_match_not_composing_requirement_name = search(requirement_name_regex, line)
                if first_match_not_composing_requirement_name is None:
                    requirement = line.lower()
                    version_constraint = None
                    unversioned_requirements.add(requirement)
                else:
                    requirement_name_end_character_index = first_match_not_composing_requirement_name.start()
                    requirement = line[:requirement_name_end_character_index].lower()
                    version_constraint = line[requirement_name_end_character_index:].strip()
                    requirements_to_version_contraints[requirement] = version_constraint
            elif line.startswith("-r"):
                dependency_group = line.strip().split()[1][:-4].replace(f"{REQUIREMENTS_FILE_NAME_BASE}", "")
                if not dependency_group:
                    dependency_group = ENVIRONMENT_NAME_FOR_CHARM
                else:
                    dependency_group = dependency_group[1:]  # removing the hyphen too
                nested_dependency_groups.add(dependency_group)

        if unversioned_requirements:
            # in case .in files contain any repeated requirements:
            for requirement in requirements_to_version_contraints:
                if requirement in unversioned_requirements:
                    unversioned_requirements.remove(requirement)

            with open(txt_file, "r") as file:
                content = file.read()
            for line in content.splitlines():
                if not line or line[0] in (" ", "#"):
                    continue
                requirement_name_end_character_index = search(requirement_name_regex, line).start()
                requirement = line[:requirement_name_end_character_index]
                version = line[requirement_name_end_character_index + 2:]  # excluding "=="
                if requirement in unversioned_requirements:
                    unversioned_requirements.remove(requirement)
                    requirements_to_version_contraints[requirement] = f"^{version}"  # caret pinning

        assert not unversioned_requirements

        remove(in_file_path)
        remove(txt_file)

    return requirements_to_version_contraints, nested_dependency_groups


def update_charmcraft(_dir: Path) -> None:
    charmcraft_path = _dir / "charmcraft.yaml"

    with open(charmcraft_path, "r") as file:
        original_charmcraft_lines = file.read().splitlines()

    updated_charmcraft_lines = []

    # adding all before "parts":
    line_index = 0
    while not original_charmcraft_lines[line_index].startswith("parts:"):
        updated_charmcraft_lines.append(original_charmcraft_lines[line_index])
        line_index += 1
    updated_charmcraft_lines.append(original_charmcraft_lines[line_index])
    line_index += 1

    # adding the intermediate, modified lines of "parts":
    with open(PATH_FOR_MODIFIED_CHARMCRAFT_LINES, "r") as file:
        intermediate_modified_charmcraft_lines = file.read().splitlines()
    for line in intermediate_modified_charmcraft_lines:
        updated_charmcraft_lines.append(line)

    # finding the starting index of the "files" part:
    line_index = len(original_charmcraft_lines) - 1
    while not original_charmcraft_lines[line_index].startswith("  files:"):
        line_index -= 1

    # adding the "files" part with the comments above:
    while line_index < len(original_charmcraft_lines):
        updated_charmcraft_lines.append(original_charmcraft_lines[line_index])
        line_index += 1

    updated_charmcraft_lines.append("")

    with open(charmcraft_path, "w") as file:
        file.write("\n".join(updated_charmcraft_lines))


def update_lock_file_and_exported_charm_requirements(_dir: Path) -> bool:
    script_name = "update-lock-file-and-export-charm-requirements.sh"
    script_path_in_repo = _dir / script_name

    copy(script_name, script_path_in_repo)

    try:
        check_call(["/bin/bash", script_name], cwd=_dir, stdout=DEVNULL, stderr=DEVNULL)
        return True
    except CalledProcessError:
        return False
    finally:
        remove(script_path_in_repo)


def update_pyproject_toml(_dir: Path, project_name: str, poetry_group_names_to_versioned_requirements: OrderedDict[str, Dict[str, str]]) -> None:
    pyproject_toml_file_path = _dir / "pyproject.toml"

    if not exists(pyproject_toml_file_path):
        with open(pyproject_toml_file_path, "w") as file:
            pass

    with open(pyproject_toml_file_path, "r") as file:
        pyproject_toml_content = toml_load(file)

    project_section = table()
    project_section.add("name", project_name)
    project_section.add("requires-python", ">=3.12,<4.0")
    pyproject_toml_content["project"] = project_section

    if "tool" not in pyproject_toml_content:
        pyproject_toml_content["tool"] = table()

    poetry_section = table()
    poetry_section.add("package-mode", False)
    pyproject_toml_content["tool"]["poetry"] = poetry_section

    pyproject_toml_content["tool"]["poetry"]["group"] = table()

    for group_name, environment_requirements_to_version_contraints in poetry_group_names_to_versioned_requirements.items():
        if not environment_requirements_to_version_contraints and group_name == ENVIRONMENT_NAME_FOR_CHARM:
            continue

        group_section = table()
        group_section.add("optional", True)
        pyproject_toml_content["tool"]["poetry"]["group"][group_name] = group_section

        group_dependency_section = table()
        for dependency, version_constraint in environment_requirements_to_version_contraints.items():
            group_dependency_section.add(dependency, version_constraint)
        pyproject_toml_content["tool"]["poetry"]["group"][group_name]["dependencies"] = group_dependency_section

    with open(pyproject_toml_file_path, "w") as file:
        toml_dump(pyproject_toml_content, file)


def update_tox_ini(_dir: Path, are_there_subcharms: bool) -> OrderedDict[str, Dict[str, str]]:
    tox_ini_file_path = _dir / "tox.ini"

    # removing the first comment lines to then add them back at the end for
    # the subsequent trick of preserving comments to be feasible:
    with open(tox_ini_file_path, "r") as file:
        lines = file.read().splitlines(keepends=True)
    copyright_lines = []
    for line in lines:
        if line.startswith("#") or line == "\n":
            copyright_lines.append(line)
        else:
            break
    with open(tox_ini_file_path, "w") as file:
        file.writelines(lines[len(copyright_lines):])

    # tricking ConfigParser into believing that lines starting with "#" or ";"
    # are not comments but keys without a value:
    # https://stackoverflow.com/questions/21476554/update-ini-file-without-removing-comments
    tox_ini_parser = ConfigParser(comment_prefixes="€", allow_no_value=True)

    tox_ini_parser.read(tox_ini_file_path)

    tox_ini_parser.set("testenv", "deps", "\npoetry>=2.1.3")

    environment_prefix = "testenv:"
    poetry_group_names_to_versioned_requirements = OrderedDict()

    poetry_group_names_to_versioned_requirements[ENVIRONMENT_NAME_FOR_CHARM], nested_dependency_groups = (
        read_versioned_requirements_and_remove_files(file_dir=_dir, file_name_base=REQUIREMENTS_FILE_NAME_BASE)
    )
    assert not nested_dependency_groups

    for section_name in tox_ini_parser.sections():
        if not section_name.startswith(environment_prefix):
            continue

        environment_name_in_tox = section_name[len(environment_prefix):]
        try:
            environment_dependencies = tox_ini_parser.get(section_name, "deps")
        except NoOptionError:
            continue
        if environment_name_in_tox != ENVIRONMENT_NAME_FOR_UPDATE_REQUIREMENTS:
            environment_dependency_filename = environment_dependencies.strip()[3:-4]
            group_name_in_poetry = environment_dependency_filename.replace(f"{REQUIREMENTS_FILE_NAME_BASE}-", "")
            group_requirements_to_version_contraints, nested_dependency_groups = (
                read_versioned_requirements_and_remove_files(file_dir=_dir, file_name_base=environment_dependency_filename)
            )
            poetry_group_names_to_versioned_requirements[group_name_in_poetry] = group_requirements_to_version_contraints

        if environment_name_in_tox == ENVIRONMENT_NAME_FOR_UPDATE_REQUIREMENTS:
            tox_ini_parser.remove_option(section_name, "allowlist_externals")
            tox_ini_parser.set(
                section_name,
                "commands",
                "\n".join(
                    (
                        "\n# updating all groups' locked dependencies:",
                        "poetry lock --regenerate",
                        "# updating all groups' locked dependencies for every subcharm folder:",
                        """find charms/ -maxdepth 1 -mindepth 1 -type d -exec bash -c "cd {} && poetry lock --regenerate" \;""",
                    ) if are_there_subcharms else (
                        "\n# updating all groups' locked dependencies:",
                        "poetry lock --regenerate",
                    )
                )
            )
            tox_ini_parser.set(
                section_name,
                "description",
                "Update requirements including those in subdirs"
            )

        else:
            commands_pre = f"\npoetry install --only {",".join(nested_dependency_groups.union({group_name_in_poetry}))}"
            tox_ini_parser.set(section_name, "commands_pre", commands_pre)

            # letting codespell ignore poetry's lock file, when codespell is employed:
            stringified_commands = tox_ini_parser.get(section_name, "commands")
            if "codespell" in stringified_commands:
                lines = stringified_commands.splitlines(keepends=True)
                updated_lines = []
                line_index = 0
                while not lines[line_index].strip().startswith("codespell"):
                    updated_lines.append(lines[line_index])
                    line_index += 1
                while line_index < len(lines) and lines[line_index].strip().endswith(" \\"):
                    updated_lines.append(lines[line_index])
                    line_index += 1
                if line_index < len(lines):
                    updated_lines.append(lines[line_index])
                    line_index += 1
                updated_lines[-1] = f"{updated_lines[-1][:-1]} \\\n"
                updated_lines.append("--skip {toxinidir}/./poetry.lock\n")
                while line_index < len(lines):
                    updated_lines.append(lines[line_index])
                    line_index += 1
                tox_ini_parser.set(section_name, "commands", "".join(updated_lines))

        tox_ini_parser.remove_option(section_name, "deps")
        tox_ini_parser.set(section_name, "skip_install", "true")

    with open(tox_ini_file_path, "w") as file:
        tox_ini_parser.write(file)

    # adding back the first comment lines for the above-mentioned trick, while
    # also removing the sporious, duplicate final whitespace:
    with open(tox_ini_file_path, "r") as file:
        lines = file.read().splitlines(keepends=True)
    with open(tox_ini_file_path, "w") as file:
        file.writelines(copyright_lines + lines[:-1])

    return poetry_group_names_to_versioned_requirements


def update_tox_installation_and_checkout_actions(content: str) -> str:
    return (
        content
        .replace("actions/checkout@v2", "actions/checkout@v4")
        .replace("actions/checkout@v3", "actions/checkout@v4")
        .replace("pip install tox", "pipx install tox")
    )


if __name__ == "__main__":
    main()
