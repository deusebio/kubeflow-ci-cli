import os
import shutil
import subprocess
import sys

import oyaml as yaml

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

logger = setup_logging(log_level="INFO", logger_name=__name__)

with open("./credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

tmp_folder = f"/home/ubuntu/tmp/kfcicli/charm_repos"
logger.info(f"Using temporary directory: {tmp_folder}")

filename=Path("../../presets/kubeflow-part2.yaml")

client = KubeflowCI.read(
    filename=filename,
    base_path=Path(f"{tmp_folder}"),
    credentials=credentials
)

CURRENT_FOLDER = Path(__file__).parent

def update_deps(script: Path, path: Path) -> bool:

    shutil.copy(script, path / script.name)

    try:
        subprocess.check_call(["/bin/bash", script.name],
                              cwd=path,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        os.remove(path / script.name )

        
def remove_python_38_block(text: str) -> str:
    lines = text.splitlines()
    result = []
    skip = False
    skip_next_line = False

    for i in range(len(lines)):
        line = lines[i]

        if skip_next_line:
            skip_next_line = False
            if line.strip() == "":
                continue

        # Check for start of the block to remove
        if (
            line.strip() == "- name: Set up Python 3.8" and
            i + 2 < len(lines) and
            "uses: actions/setup-python@v5.3.0" in lines[i + 1] and
            "python-version: 3.8" in lines[i + 3]
        ):
            skip = True
            continue  # Skip the current line

        if skip:
            # End block after the "with:" and "python-version" lines
            if "python-version: 3.8" in line:
                skip = False
                skip_next_line = True
            continue  # Skip all lines in the block

        result.append(line)

    return "\n".join(result) + "\n"

# Remove all instances of constraints.txt
def remove_all_constraints_txt(base_path: Path):
    for file in base_path.rglob("constraints.txt"):
        if file.is_file():
            file.unlink()

# Replace all references to use base 24.04            
def replace_base_text(base_path: Path):
    for f in base_path.rglob("*"):
        if f.is_file():
            try:
                content = f.read_text()
            except UnicodeDecodeError:
                continue
            new_content = content.replace("ubuntu-20.04", "ubuntu@24.04")
            new_content = new_content.replace("ubuntu@20.04", "ubuntu@24.04")
            if new_content != content:
                f.write_text(new_content)
                logger.info(f"Updated: {f}")


def update_base(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):

    for charm in charms:

        charm_folder = ( repo.base_path / charm.tf_module ).parent

        shutil.copy(CURRENT_FOLDER / "charmcraft.yaml", charm_folder / "charmcraft.yaml" )

        if repo.is_dirty():
            repo.update_branch(
                commit_msg=f"updating charmcraft for charm {charm.name}",
                directory=".",
                push=not dry_run, force=True
            )

        success = update_deps(CURRENT_FOLDER / "update-deps.sh", charm_folder )

        if not success:
            logging.warning(f"Failing to update dependencies on charm {charm.name}")

        if success and repo.is_dirty():
            repo.update_branch(
                commit_msg=f"updating deps for charm {charm.name}",
                directory=".",
                push=not dry_run, force=True
            )

    success = update_deps(CURRENT_FOLDER / "update-deps.sh", repo.base_path)
            

    logger.info("Updating 20.04 with 24.04 in all files.")
    replace_base_text(repo.base_path)

    logger.info("Deleting unecessary constraints.txt files.")
    remove_all_constraints_txt(repo.base_path)
            
    for ci_file in (repo.base_path / ".github" / "workflows").glob("*.yaml"):
        logger.info(f"Updating file {ci_file}")
        with open(ci_file, "r") as fid:
            content = fid.read()
        new_content = remove_python_38_block(content)
            
        hash_1 = hash(content)

        hash_2 = hash(new_content)

        if hash_1 != hash_2:
            logger.info(f"Changes detected in file {ci_file}. Overwriting...")
            with open(ci_file, "w") as fid:
                fid.write(new_content)
        else:
            logger.info(f"No changes found in file {ci_file}")

    if repo.is_dirty():
        repo.update_branch(
            commit_msg=f"Updating GitHub action file", directory=".",
            push=not dry_run, force=True
        )

with open("body.md", "r") as f:
    pr_body = f.read()

client.canon_run(
    wrapper_func=update_base,
    branch_name="kf-7472-update-base",
    title="chore: Update bases to 24.04 and charm dependencies",
    body=pr_body,
    dry_run=False
)
