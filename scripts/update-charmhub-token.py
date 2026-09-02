from kfcicli.main import *
from kfcicli.utils import setup_logging
import json

from github.Repository import Repository

logger = setup_logging(log_level="INFO")

def update_repository(
    github_repo: Repository,
    environment_name: str,
    secret_name: str,
    secret_value: str,
    dry_run: bool,
) -> None:
    """Create the environment in the repository and add the secret to it."""
    if dry_run:
        logger.info(
            f"[dry-run] Would set `{secret_name}` in `{environment_name}` of `{github_repo.full_name}`"
        )
        return

    environment = github_repo.create_environment(environment_name)
    environment.create_secret(secret_name, secret_value)
    logger.info(f"Set `{secret_name}` in environment `{environment_name}` of `{github_repo.full_name}`")


def update_charmhub_token(repo: Client, charms: list[LocalCharmRepo], dry_run: bool):
    charms_list = " ".join([f"--charm {n.metadata.name}" for n in charms])

    logger.info("Building charmcraft command")

    cmd_str = "charmcraft login --quiet " + charms_list + \
              " --ttl 31536000 " + \
              "--permission package-manage-releases --permission package-manage-revisions --permission package-view-revisions " + \
              "--export /dev/stdout"

    print(cmd_str)
    token = input("Copy and paste the token\n")

    if not token:
        logger.warning("Token empty: SKIPPING")
        return

    logger.info("Updating charmhub token")

    update_repository(repo._github_repo, "edge-pr", "CHARMHUB_TOKEN_EDGE_PR", token, dry_run=dry_run)
    update_repository(repo._github_repo, "edge", "CHARMHUB_TOKEN_EDGE", token, dry_run=dry_run)

    logger.info("charmhub token updated!")

if __name__ == "__main__":
    import argparse
    import os

    home_folder = os.getenv("HOME", "/home/ubuntu")

    parser = argparse.ArgumentParser()

    parser.add_argument("--file", required=True)
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print release commands without executing them (default)",
    )
    action_group.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Execute charmcraft release commands",
    )
    parser.set_defaults(dry_run=True)

    parser.add_argument(
        "--base-path", required=False, default=f"{home_folder}/tmp/kfcicli", help="Base path where to store all repositories"
    )
    parser.add_argument(
        "--credentials", required=False, default=f"{home_folder}/.kfcicli/credentials.json", help="File holding the credentials for Github"
    )

    args = parser.parse_args()

    with open(args.credentials, "r") as fid:
        credentials = GitCredentials(**json.loads(fid.read()))

    base_path = Path(args.base_path)
    repository_file = Path(args.file)

    client = KubeflowCI.read(repository_file, base_path, credentials)

    if args.dry_run:
        logger.info("Running in DRY-RUN mode")

    for repo in client.repos:
        charms = repo.charms
        update_charmhub_token(repo.repository, charms, args.dry_run)
