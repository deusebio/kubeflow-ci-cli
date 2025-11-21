#!/usr/bin/env python3
"""
Script to update data-platform-workflows version from v29 to v38 in GitHub workflow files.

This script replicates the changes from PR:
https://github.com/canonical/notebook-operators/pull/515/files

Changes:
- Update data-platform-workflows version from any version to v38.0.0
- Replace channel-based approach with track-based approach
- Update workflow file references (release_charm.yaml -> release_charm_pr.yaml and release_charm_edge.yaml)
"""

import os
import re
import sys
from pathlib import Path


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

logger = setup_logging(log_level="INFO", logger_name=__name__)


def update_ci_yaml(repo_path: Path) -> bool:
    """Update ci.yaml workflow file with v38 changes."""
    file_path = repo_path / ".github" / "workflows" / "ci.yaml"
    
    if not file_path.exists():
        logger.warning(f"{file_path} does not exist, skipping")
        return False

    content = file_path.read_text()
    original_content = content

    # Replace get-charm-paths-channel with get-charm-paths-track
    content = content.replace("get-charm-paths-channel:", "get-charm-paths-track:")
    content = content.replace("get-charm-paths-channel", "get-charm-paths-track")
    
    # Replace channel output key with track (in workflow_call outputs section)
    # This handles the case where "channel:" is used as an output key
    content = re.sub(
        r'(\s+)(channel:)\s*\n(\s+description: Charmhub)',
        r'\1track:\n\3',
        content
    )
    
    # Replace charm-channel with track in outputs
    content = content.replace("charm-channel:", "track:")
    content = content.replace(
        "description: Charmhub channel the charms are released to",
        "description: Charmhub track determined from branch name"
    )
    content = content.replace(
        "value: ${{ jobs.get-charm-paths-channel.outputs.charm-channel }}",
        "value: ${{ jobs.get-charm-paths-track.outputs.track }}"
    )
    
    # Replace job name
    content = content.replace(
        "name: Get charm paths and charmhub channel",
        "name: Get charm paths and track"
    )
    
    # Replace output in job - all variations
    content = content.replace(
        "charm-channel: ${{ steps.select-channel.outputs.name }}",
        "track: ${{ steps.determine-track.outputs.track }}"
    )
    content = content.replace(
        "track: ${{ steps.select-channel.outputs.name }}",
        "track: ${{ steps.determine-track.outputs.track }}"
    )
    
    # Replace the channel selection step with track determination
    old_step = """      - name: Select charmhub channel
        uses: canonical/charming-actions/channel@2.6.2
        id: select-channel"""
    
    new_step = """      - name: Determine track
        id: determine-track
        shell: python
        run: |
          import os
          
          if "${{ github.event_name }}" == "pull_request":
              ref = "${{ github.base_ref }}"
          else:
              ref = "${{ github.ref_name }}"
          
          if ref.startswith("track/"):
              track = ref.removeprefix("track/")
          else:
              track = "latest"
          
          with open(os.environ["GITHUB_OUTPUT"], "a") as f:
              f.write(f"track={track}\\n")
          
          print(f"Track: {track}")"""
    
    content = content.replace(old_step, new_step)
    
    # Update data-platform-workflows version to v38.0.0 (any previous version)
    content = re.sub(
        r'uses: canonical/data-platform-workflows/\.github/workflows/build_charm\.yaml@v[\d.]+',
        'uses: canonical/data-platform-workflows/.github/workflows/build_charm.yaml@v38.0.0',
        content
    )
    
    # Change release_charm.yaml to release_charm_pr.yaml and update version
    content = re.sub(
        r'uses: canonical/data-platform-workflows/\.github/workflows/release_charm\.yaml@v[\d.]+',
        'uses: canonical/data-platform-workflows/.github/workflows/release_charm_pr.yaml@v38.0.0',
        content
    )
    
    # Replace channel: with track: in release job (all variations)
    content = content.replace(
        "channel: ${{ needs.get-charm-paths-channel.outputs.charm-channel }}",
        "track: ${{ needs.get-charm-paths-track.outputs.track }}"
    )
    content = content.replace(
        "channel: ${{ needs.get-charm-paths-track.outputs.charm-channel }}",
        "track: ${{ needs.get-charm-paths-track.outputs.track }}"
    )
    content = content.replace(
        "channel: ${{ needs.get-charm-paths-track.outputs.track }}",
        "track: ${{ needs.get-charm-paths-track.outputs.track }}"
    )
    
    # Remove create-git-tags line
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if 'create-git-tags: false' not in line:
            new_lines.append(line)
    content = '\n'.join(new_lines)
    
    if content != original_content:
        file_path.write_text(content)
        logger.info(f"✓ Updated {file_path}")
        return True
    else:
        logger.info(f"- No changes needed for {file_path}")
        return False


def update_release_yaml(repo_path: Path) -> bool:
    """Update release.yaml workflow file with v38 changes."""
    file_path = repo_path / ".github" / "workflows" / "release.yaml"
    
    if not file_path.exists():
        logger.warning(f"{file_path} does not exist, skipping")
        return False

    content = file_path.read_text()
    original_content = content

    # Change release_charm.yaml to release_charm_edge.yaml and update version to v38.0.0
    content = re.sub(
        r'uses: canonical/data-platform-workflows/\.github/workflows/release_charm\.yaml@v[\d.]+',
        'uses: canonical/data-platform-workflows/.github/workflows/release_charm_edge.yaml@v38.0.0',
        content
    )
    
    # Replace channel: with track:
    content = content.replace(
        "channel: ${{ needs.ci-tests.outputs.channel }}",
        "track: ${{ needs.ci-tests.outputs.track }}"
    )
    
    if content != original_content:
        file_path.write_text(content)
        logger.info(f"✓ Updated {file_path}")
        return True
    else:
        logger.info(f"- No changes needed for {file_path}")
        return False


def process_repo(repo: Client, charms: list[LocalCharmRepo], dry_run: bool = False):
    """Process a single repository to update data-platform-workflows."""
    logger.info(f"Processing repository at: {repo.base_path}")
    
    changes_made = []
    
    # Update ci.yaml
    if update_ci_yaml(repo.base_path):
        changes_made.append("ci.yaml")
    
    # Update release.yaml
    if update_release_yaml(repo.base_path):
        changes_made.append("release.yaml")
    
    if changes_made:
        logger.info(f"✓ Successfully updated {len(changes_made)} file(s): {', '.join(changes_made)}")
        
        # Commit the changes
        if repo.is_dirty():
            commit_message = "chore: update data platform workflows version to v38"
            repo.update_branch(commit_msg=commit_message, directory=".", push=not dry_run, force=True)
            logger.info(f"✓ Committed changes: {commit_message}")
    else:
        logger.info("- No changes were needed")
    
    return len(changes_made) > 0


if __name__ == "__main__":
    with open("./credentials.json", "r") as fid:
        credentials = GitCredentials(**json.loads(fid.read()))

    base_path = Path(__file__).parent.parent.parent / "repos"

    filename = Path("./presets/kubeflow-multi-charm.yaml")

    client = KubeflowCI.read(
        filename=filename,
        base_path=base_path,
        credentials=credentials
    )

    with open(Path(__file__).parent / "body.md", "r") as f:
        pr_body = f.read()

    client.canon_run(
        wrapper_func=process_repo,
        branch_name="chore-update-dpw-v38",
        title="chore: update data platform workflows to v38.0.0",
        body=pr_body,
        dry_run=False
    )