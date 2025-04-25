import json

from kfcicli.main import *
from kfcicli.utils import setup_logging

setup_logging(log_level="INFO")

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

base_path = ...
repository_file = Path("presets/release-1.10.yaml")

client = KubeflowCI.read(repository_file, base_path, credentials)

client.cut_release(
    "kf-7254-release-1.10",
    title="[KF-7254] Release 1.10",
    juju_tf_version=">= 0.14.0",
    dry_run=False
)
