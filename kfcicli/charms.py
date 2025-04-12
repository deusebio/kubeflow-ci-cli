import re
import hcl2

from dataclasses import dataclass
from git import Repo

from typing import Iterator
from kfcicli.terraform import get_juju_applications_names

from kfcicli.metadata import InputError
from pathlib import Path

@dataclass
class CharmRepo:
    name: str
    url: str
    tf_module: str
    branch: str

def parse_repos_from_module(filename: Path) -> list[CharmRepo]:

    with open(filename, 'r') as file:
        out = hcl2.load(file)

    pattern = re.compile(r".*(http.*)\/\/([\w,\/,-]*)\?ref=([\w,\/,\.,-]*)")

    return [
        CharmRepo(
            name=charm_name,
            url=regex_match.group(1),
            tf_module=regex_match.group(2),
            branch=regex_match.group(3)
        )
        for module in out["module"]
        for charm_name, properties in module.items()
        if (regex_match := pattern.match(properties["source"]))
    ]


def parse_repos_from_path(path: Path) -> Iterator[CharmRepo]:

    for folder in path.iterdir():
        repo = Repo(str(folder))

        for dirpath, dirnames, filenames in folder.walk():
            dirpath: Path
            if "main.tf" in filenames:
                apps =  list(get_juju_applications_names(dirpath / "main.tf"))

                if len(apps)>1:
                    raise InputError(f"too many applications in folder {dirpath}")

                yield CharmRepo(apps[0], repo.remote().url, str(dirpath.relative_to(folder)), repo.active_branch.name)
