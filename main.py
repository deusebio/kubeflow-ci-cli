from kfcicli.main import *
import json

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

# filename = "/home/deusebio/Canonical/data-platform/repos/kubeflow/charmed-kubeflow-solutions/modules/kubeflow/applications.tf"
repos = list(download_repos(
    [Path(
        "/tmp/enrico/main_repo/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path("/tmp/enrico/main_repo/charm_repos"),
    credentials=credentials, input_branch="main"
))

cut_release(
    "wip-test",
    [Path("/tmp/enrico/main_repo/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path("/tmp/enrico/main_repo/charm_repos"),
    credentials=credentials,
    title="[KF-XXXX] Release 1.10",
    juju_tf_version=">=0.14.0"
)


summary(
    "wip-test",
    [Path("/tmp/enrico/main_repo/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    Path("/tmp/enrico/main_repo/charm_repos"),
    credentials=credentials
)