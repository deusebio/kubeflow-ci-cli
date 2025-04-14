from kfcicli.main import *
import json

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))


tmp_folder = "/home/deusebio/tmp/kfcicli"


client = KubeflowCI(
    modules=[Path(f"{tmp_folder}/charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    base_path=Path(f"{tmp_folder}/charm_repos"),
    credentials=credentials
)


# filename = "/home/deusebio/Canonical/data-platform/repos/kubeflow/charmed-kubeflow-solutions/modules/kubeflow/applications.tf"
repos = list(client.iter_repos())

client.cut_release(
    "wip-test",
    title="[KF-XXXX] Release 1.10",
    juju_tf_version=">=0.14.0"
)

client.summary_pull_request("wip-test")

client.summary_images()

client.update_image_tags("wip-test-update")
