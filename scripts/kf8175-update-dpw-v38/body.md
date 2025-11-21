Updates the CI to use the latest version of data platform workflows from `v29.0.0` to `v38.0.0`
Ref https://github.com/canonical/bundle-kubeflow/issues/1372

## Summary
* Replaces `channel` input with `track` in `release` job, to comply with the breaking change made in https://github.com/canonical/data-platform-workflows/pull/295
* Refactors `get-charm-paths-channel` to compute the track instead of the channel and renamed to `get-charm-paths-track` (see point above)
* Due to the breaking change in https://github.com/canonical/data-platform-workflows/pull/295:
  * In `ci.yaml`, change reused workflow `canonical/data-platform-workflows/.github/workflows/release_charm.yaml` to `canonical/data-platform-workflows/.github/workflows/release_charm_pr.yaml`
  * In `release.yaml`, change reused workflow `canonical/data-platform-workflows/.github/workflows/release_charm.yaml` to `canonical/data-platform-workflows/.github/workflows/release_charm_edge.yaml`
  * Remove `create-tags: false` input, note: not passing create-git-tags: false anymore does not mean we now create tags; in fact, this is coherent with the new workflow for pull requests, which not only does not have this input but also does not create tags