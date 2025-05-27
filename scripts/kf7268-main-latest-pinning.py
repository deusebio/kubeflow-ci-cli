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
