# Kubeflow CI Python Toolkit

Python package for providing utilities to manage the Kubeflow CI. 

## Basic Usage

To use the package first put your Github credentials in a file

```python
# credentials.json
{
    "username": <github user>
    "access_token": <access_token>
}
```

Load the credentials into a `GitCredential` object, and pick a folder where to store all repositories

```python
from kfcicli.main import *
import json
import os

with open("credentials.json", "r") as fid:
    credentials = GitCredentials(**json.loads(fid.read()))

tmp_folder = f"/home/os.getenv('HOME')/tmp/kfcicli/charm_repos"
```

You can then instantiate a `KubeflowCI` object to manage your CI, by providing the modules to be used to retrieve charm informations, e.g. 

```python
from kfcicli.main import KubeflowCI
from pathlib import Path

client = KubeflowCI(
    modules=[Path(f"../charmed-kubeflow-solutions/modules/kubeflow/applications.tf")],
    base_path=Path(f"{tmp_folder}"),
    credentials=credentials
)
```

At this point you have your environment setup. You can start by retrieving all repositories:

```python
client.repos
```

The `repos` variable is a list of `kfciclie.kubeflow.KubeflowRepo` that has two parts:

```python
KubeflowRepo(<kfcicli.repository.Client>, [<kfcicli.repository.CharmRepo>])
```

with 
* `Client` being the abstraction to interact with the Git repo and its linked Github repository, 
* `CharmRepo` being a reference to a particular charm within a Git repository. There exists two classes: `CharmRepo` and `LocalCharmRepo`. `CharmRepo` is the one parsed out from the Terraform module, whereas `LocalCharmRepo` also provides reference to the path where the charm is found and also bindings to metadata information (e.g. name, images, etc).

You can also dump the list of `KubeflowRepo` representation into a YAML file with 

```python
client.dump("my-file.yaml")
```

To be used to re-read the data into a `KubeflowCI` object

```python
client = KubeflowCI.dump("my-file.yaml")
```

Using the `client` object is possible to do multiple things (internally all the functions below uses that), like:

1. Cutting release branches and updating `channel` information and terraform provider versions:
```python
client.cut_release(
    "kf-xxxx-release-yyyyy",
    title="[KF-XXXX] Release 1.10",
    juju_tf_version=">=0.14.0"
)
```
This will open on each repository a PR against the release branch just created where the information are updated. The PR branch will take the provided name, e.g. `kf-xxxx-release-yyyyy`.

2. Provide a summary of all pull-requested tracking a given branch:
```python
pr = client.pull_request("kf-xxxx-release-yyyyy")
```

The `pr` object exposes a few methods to either show a summary of the PRs (e.g. as pandas Dataframe with `.df` or simple table with `.table`), or also 
allow automatic merging using `.merge()`.

3. Provide a summary of all images used in the various charms, and provide information about the latest tag present in the linked container registry
```python
client.summary_images()
```

4. Compare the current and the latest tag in the container registry and raise a PR to update it against the release branch. 
```python
client.update_image_tags("wip-test-update")
```
