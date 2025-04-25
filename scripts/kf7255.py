from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

setup_logging(log_level="INFO")

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

base_path = ...

filename=Path("./presets/kubeflow-repos.yaml")

client = KubeflowCI.read(
    filename=filename,
    base_path=base_path,
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

