import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import hcl2
from git import Repo

from kfcicli.metadata import InputError
from kfcicli.metadata import get as get_metadata, Metadata
from kfcicli.terraform import get_juju_applications_names

METADATA = "metadata.yaml"
TERRAFORM_MAIN = "main.tf"
TERRAFORM_DIR = "terraform"


@dataclass
class CharmRepo:
    name: str
    url: str
    tf_module: Path
    branch: str


@dataclass
class LocalCharmRepo(CharmRepo):
    metadata: Metadata

    @classmethod
    def from_charm_repo(cls, charm_repo: CharmRepo, metadata: Metadata):
        return LocalCharmRepo(
            name=charm_repo.name,
            url=charm_repo.url,
            tf_module=charm_repo.tf_module,
            branch=charm_repo.branch,
            metadata=metadata
        )


def parse_repos_from_module(filename: Path) -> list[CharmRepo]:
    with open(filename, 'r') as file:
        out = hcl2.load(file)

    pattern = re.compile(r".*(http.*)\/\/([\w,\/,-]*)\?ref=([\w,\/,\.,-]*)")

    return [
        CharmRepo(
            name=charm_name,
            url=regex_match.group(1),
            tf_module=Path(regex_match.group(2)),
            branch=regex_match.group(3)
        )
        for module in out["module"]
        for charm_name, properties in module.items()
        if (regex_match := pattern.match(properties["source"]))
    ]


EXCLUDE_DIRS = ["tests"]


def parse_repos_from_path(path: Path, exclude: list[str] = EXCLUDE_DIRS) -> \
Iterator[LocalCharmRepo]:
    for folder in path.iterdir():
        repo = Repo(str(folder))

        for dirpath, dirnames, filenames in folder.walk(top_down=True):
            dirpath: Path
            dirnames[:] = [d for d in dirnames if d not in exclude]

            if METADATA in filenames:
                metadata = get_metadata(dirpath)

                if not (dirpath / TERRAFORM_DIR).exists():
                    raise InputError(
                        f"terraform module does not exist in {dirpath}")

                apps = list(get_juju_applications_names(
                    dirpath / TERRAFORM_DIR / TERRAFORM_MAIN))

                if len(apps) > 1:
                    raise InputError(
                        f"too many applications in folder {dirpath}")

                yield LocalCharmRepo(
                    name=apps[0],
                    url=repo.remote().url,
                    tf_module=(dirpath / TERRAFORM_DIR).relative_to(folder),
                    branch=repo.active_branch.name,
                    metadata=metadata
                )
