# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for parsing metadata.yaml file."""
from enum import StrEnum
from pathlib import Path

import yaml
from typing import NamedTuple

CHARMCRAFT_FILENAME = "charmcraft.yaml"
CHARMCRAFT_NAME_KEY = "name"
CHARMCRAFT_LINKS_KEY = "links"
CHARMCRAFT_LINKS_DOCS_KEY = "documentation"
METADATA_DOCS_KEY = "docs"
METADATA_FILENAME = "metadata.yaml"
METADATA_NAME_KEY = "name"
METADATA_RESOURCE = "resources"


class SourceMetadata(StrEnum):
    METADATA="metadata.yaml"
    CHARMCRAFT="charmcraft.yaml"

class Metadata(NamedTuple):
    """Information within metadata file. Refer to: https://juju.is/docs/sdk/metadata-yaml.

    Only name and docs are the fields of interest for the scope of this module.

    Attrs:
        name: Name of the charm.
        docs: A link to a documentation cover page on Discourse.
    """
    file: Path
    name: str
    docs: str | None
    resources: dict
    source: SourceMetadata


class InputError(Exception):
    """A problem with the user input occurred."""

def get(path: Path) -> Metadata:
    """Check for and read the metadata.

    The charm metadata can be in the file metadata.yaml or in charmcraft.yaml.
    From charmcraft version 2.5, the information should be in charmcraft.yaml,
    and the user should only modify that file. This function does not consider
    the case in which the name is in one file and the doc link is in the other.

    Args:
        path: The base path to look for the metadata files.

    Returns:
        The contents of the metadata file.

    Raises:
        InputError: if the metadata file does not exist or is malformed.

    """
    metadata_yaml = path / METADATA_FILENAME
    if metadata_yaml.is_file():
        return _parse_metadata_yaml(metadata_yaml)

    charmcraft_yaml = path / CHARMCRAFT_FILENAME
    if charmcraft_yaml.is_file():
        return _parse_charmcraft_yaml(charmcraft_yaml)

    raise InputError(
        f"Could not find {METADATA_FILENAME} or {CHARMCRAFT_FILENAME} files"
        f", looked in folder: {path}"
    )


def _parse_metadata_yaml(metadata_yaml: Path) -> Metadata:
    """Parse metadata file.

    Args:
        metadata_yaml: The file path the the metadata file.

    Returns:
        The contents of the metadata file.

    Raises:
        InputError: if the metadata file does not exist or are malformed.
    """
    try:
        metadata = yaml.safe_load(metadata_yaml.read_text())
    except yaml.error.YAMLError as exc:
        raise InputError(
            f"Malformed {METADATA_FILENAME} file, read file: {metadata_yaml}"
        ) from exc

    if not metadata:
        raise InputError(f"{METADATA_FILENAME} file is empty, read file: {metadata_yaml}")
    if not isinstance(metadata, dict):
        raise InputError(
            f"{METADATA_FILENAME} file does not contain a mapping at the root, "
            f"read file: {metadata_yaml}, content: {metadata!r}"
        )

    if METADATA_NAME_KEY not in metadata:
        raise InputError(
            f"Could not find required key: {METADATA_NAME_KEY}, "
            f"read file: {metadata_yaml}, content: {metadata!r}"
        )
    if not isinstance(name := metadata[METADATA_NAME_KEY], str):
        raise InputError(f"Invalid value for name key: {name}, expected a string value")

    docs = metadata.get(METADATA_DOCS_KEY)
    if not (isinstance(docs, str) or docs is None) or (
        METADATA_DOCS_KEY in metadata and docs is None
    ):
        raise InputError(f"Invalid value for docs key: {docs}, expected a string value")

    if METADATA_RESOURCE not in metadata:
        print(f"Missing resources in charm {name}")
        images = {}
    else:
        images = {
            key: value["upstream-source"]
            for key, value in metadata.get(METADATA_RESOURCE, {}).items()
            if value["type"] == "oci-image"
        }

    return Metadata(
        file=metadata_yaml,name=name, docs=docs, resources=images, source=SourceMetadata.METADATA
    )


def _parse_charmcraft_yaml(charmcraft_yaml: Path) -> Metadata:
    """Parse charmcraft file.

    Args:
        charmcraft_yaml: The file path the the charmcraft file.

    Returns:
        The contents of the charmcraft file.

    Raises:
        InputError: if the charmcraft file does not exist or are malformed.
    """
    try:
        charmcraft = yaml.safe_load(charmcraft_yaml.read_text())
    except yaml.error.YAMLError as exc:
        raise InputError(
            f"Malformed {CHARMCRAFT_FILENAME} file, read file: {charmcraft_yaml}"
        ) from exc

    if not charmcraft:
        raise InputError(f"{CHARMCRAFT_FILENAME} file is empty, read file: {charmcraft_yaml}")
    if not isinstance(charmcraft, dict):
        raise InputError(
            f"{CHARMCRAFT_FILENAME} file does not contain a mapping at the root, "
            f"read file: {charmcraft_yaml}, content: {charmcraft!r}"
        )

    if CHARMCRAFT_NAME_KEY not in charmcraft:
        raise InputError(
            f"Could not find required key: {CHARMCRAFT_NAME_KEY}, "
            f"read file: {charmcraft_yaml}, content: {charmcraft!r}"
        )
    if not isinstance(name := charmcraft[CHARMCRAFT_NAME_KEY], str):
        raise InputError(f"Invalid value for name key: {name}, expected a string value")

    docs = None
    links = charmcraft.get(CHARMCRAFT_LINKS_KEY)
    if links:
        if not isinstance(links, dict):
            raise InputError(
                f"{CHARMCRAFT_FILENAME} invalid value for links {CHARMCRAFT_LINKS_KEY} key."
            )

        docs = links.get(CHARMCRAFT_LINKS_DOCS_KEY)
        if not (isinstance(docs, str) or docs is None):
            raise InputError(
                f"Invalid value for documentation key: {docs}, expected a string value"
            )

    return Metadata(file=charmcraft_yaml, name=name, docs=docs, resources={}, source=SourceMetadata.CHARMCRAFT)