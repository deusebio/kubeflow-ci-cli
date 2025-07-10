Ref: https://github.com/canonical/bundle-kubeflow/issues/1277

This PR:
- Updates the dependencies using `pip-compile` with Python 3.12.
- Updates `charmcraft.yaml` to use Ubuntu `24.04` as a base. Note that we're pinning the version of `pip` to avoid issues with different versions.
- Removes the `setup-python` action in all CI workflows, since we will be using the default Python version in 24.04.
- Updates all references from the `20.04` base to the new `24.04` base.
