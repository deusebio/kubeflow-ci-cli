from kfcicli.main import *
import json

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))


tmp_folder = "/home/deusebio/tmp/kfcicli"

# filename = "/home/deusebio/Canonical/data-platform/repos/kubeflow/charmed-kubeflow-solutions/modules/kubeflow/applications.tf"
repos = list(download_repos(
    [Path(
        f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials, input_branch="main"
))

cut_release(
    "wip-test",
    [Path(f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials,
    title="[KF-XXXX] Release 1.10",
    juju_tf_version=">=0.14.0"
)

summary_pull_request(
    "wip-test",
    [Path(f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials
)

summary_images(Path(f"{tmp_folder}/charm_repos"))

update_image_tags(
   "wip-test-update",
    [Path(f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials
)
