import logging
from fileinput import filename

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

setup_logging(log_level="INFO")

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))


tmp_folder = "/home/deusebio/tmp/kfcicli"
# tmp_folder = "/home/deusebio/tmp/test"

modules = [
    Path(f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow/applications.tf"),
   Path(f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow-mlflow/main.tf"),
   Path(f"{tmp_folder}/charmed-mlflow-solutions/modules/mlflow/applications.tf")
]

client = KubeflowCI.from_tf_modules(
    modules=modules,
    base_path=Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials
)

filename = Path("presets/kubeflow-repos.yaml")

client.dump(filename)   #to_dict()




####

client.cut_release(
    "kf-7254-release-1.10",
    title="[KF-7254] Release 1.10",
    juju_tf_version=">= 0.14.0",
    dry_run=False
)


#####

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

setup_logging(log_level="INFO")

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

tmp_folder = "/home/deusebio/tmp/kfcicli"

filename=Path("./presets/kubeflow-repos.yaml")

client = KubeflowCI.read(
    filename=filename,
    base_path=Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials
)

def update_tf_provider(juju_tf_version):
    def wrapper(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):
        from kfcicli.terraform import set_version_field

        for charm in charms:
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

    return wrapper

client.canon_run(
    wrapper_func=update_tf_provider(">= 0.14.0"),
    branch_name="kf-7255-update-tf-provider",
    title="[KF-7255] Update Juju provider",
    body="Updating juju provider requirement to >=0.14.0",
    dry_run=False
)





def update_channel(channel: str):
    def wrapper(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):
        from kfcicli.terraform import set_variable_field

        for charm in charms:
            set_variable_field(
                "channel", "default",
                channel,
                filename=repo.base_path / charm.tf_module / "variables.tf"
            )

            if repo.is_dirty():
                repo.update_branch(
                    commit_msg=f"pin channel to latest/edge for charm {charm.name}", directory=".",
                    push=not dry_run, force=True
                )

    return wrapper

client.canon_run(
    wrapper_func=update_channel("latest/edge"),
    branch_name="kf-7268-pin-channel-edge",
    title="[KF-7268] chore: pin channel to latest/edge",
    body="Pin channel to latest/edge",
    dry_run=False
)




def update_tox(channel: str):
    def wrapper(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):
        for charm in charms:
            import configparser
            config = configparser.ConfigParser()

            if not (filename := charm.metadata.file.parent / "tox.ini").exists():
                continue

            config.read(filename)

            if (
                not "testenv:unit" in config.sections() or
                "coverage xml" not in config["testenv:unit"]["commands"]
            ):
                continue

            config["testenv:unit"]["commands"] += "\ncoverage xml"

            with open(filename,'w') as configfile:
                config.write(configfile)

        import requests
        import yaml
        url = "https://raw.githubusercontent.com/canonical/mongodb-operator/refs/heads/6/edge/.github/workflows/tics_run_sh_ghaction_test.yml"
        if not (response := requests.get(url)) or (response.status_code != 200):
            logging.warning(f"Bundle file {url} could not be downloaded")

        workflow = yaml.safe_load(response.content.decode("utf-8"))

        workflow["jobs"]["build"]["steps"][-1]["with"]["project"] = repo.base_path.name


# client.summary_pull_request("wip-test")

# client.summary_images()

# client.update_image_tags("wip-test-update")
