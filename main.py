import logging
from fileinput import filename

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

setup_logging(log_level="INFO")

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

tmp_folder = "/home/deusebio/tmp/kfcicli"

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

# client.dump("presets/release-1.10.yaml")

# client.summary_pull_request("wip-test")

# client.summary_images()

# client.update_image_tags("wip-test-update")




