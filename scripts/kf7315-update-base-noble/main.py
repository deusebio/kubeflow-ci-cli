import os
import shutil
import subprocess

import oyaml as yaml

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

logger = setup_logging(log_level="INFO", logger_name=__name__)

with open("/home/deusebio/.kfcicli/credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

tmp_folder = "/home/deusebio/.kfcicli"

filename=Path("./presets/kubeflow-repos.yaml")

# This only contains the adminssion-webhook and katib operators
filename=Path("./presets/test.main.yaml")

client = KubeflowCI.read(
    filename=filename,
    base_path=Path(f"{tmp_folder}"),
    credentials=credentials
)

CURRENT_FOLDER = Path(__file__).parent

def update_deps(script: Path, path: Path) -> bool:

    shutil.copy(script, path / script.name)

    try:
        subprocess.check_call(["/bin/bash", script.name], cwd=path)
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        os.remove(path / script.name )

def remove_python_step(steps: dict):
    return [
        step
        for step in steps
        if "setup-python" not in step.get("uses", "")
    ]

def add_python_step(steps: list[dict], python_version: str = "3.12"):
    idx = [
        ith for ith, step in enumerate(steps)
        if "actions/checkout" in step.get("uses", "")
    ]

    python_step = {
        "name": f"Set up Python {python_version}",
        "uses": "actions/setup-python@v5.3.0",
        "with": {"python-version": python_version}
    }

    if not idx:
        return [python_step] + steps

    return steps[:(idx[0]+1)] + [python_step] + steps[(idx[0]+1):]

def refactor_ci(ci: dict):
    from collections import OrderedDict
    jobs =  OrderedDict()
    for job_name, job in ci["jobs"].items():
        if "steps" in job:
            job["steps"] = remove_python_step(job["steps"])
            jobs[job_name] = job
        else:
            jobs[job_name] = job
    ci["jobs"] = jobs
    return ci

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

    for ci_file in (repo.base_path / ".github" / "workflows").glob("*.yaml"):

        logger.info(f"Updating file {ci_file}")
        with open(ci_file, "r") as fid:
            ci = yaml.safe_load(fid)

        hash_1 = hash(json.dumps(ci))

        new_ci = refactor_ci(ci)

        hash_2 = hash(json.dumps(new_ci))

        if hash_1 != hash_2:
            logger.info(f"Changes detected in file {ci_file}. Overwriting...")
            with open(ci_file, "w") as fid:
                yaml.dump(new_ci, fid)

            subprocess.check_output([
                "sed", '-i', 's/^true:/on:/g', str(ci_file)
            ])
        else:
            logger.info(f"No changes found in file {ci_file}")

    if repo.is_dirty():
        repo.update_branch(
            commit_msg=f"Updating GitHub action file", directory=".",
            push=not dry_run, force=True
        )

client.canon_run(
    wrapper_func=update_base,
    branch_name="kf-7315-update-base",
    title="[KF-7315] Update bases to 24.04",
    body="PR for updating bases to 24.04, and updating also python dependencies",
    dry_run=False
)
