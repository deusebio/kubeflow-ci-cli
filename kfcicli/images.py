import json

# images = [
#     "charmedkubeflow/admission-webhook:1.10.0-8dd1032",
#     "docker.io/charmedkubeflow/katib-db-manager:v0.18.0-d73ff5e"
# ]

# image: str = images[0]

from enum import StrEnum

class Platforms(StrEnum):
    DOCKER = "docker.io"
    GITHUB = "ghcr.io"


from dataclasses import dataclass

def get_platform(image: str):
    for platform in Platforms:
        if image.startswith(f"{platform.value}/"):
            return platform, image.removeprefix(f"{platform.value}/")
    return Platforms.DOCKER, image


def split_names(image: str):
    *namespace_lst, image_name = image.split("/", maxsplit=1)

    if len(namespace_lst)>1:
        raise Exception(f"Too many elements. Error when parsing {image}")

    if len(namespace_lst)==0:
        return "library", image_name
    else:
        return namespace_lst[0], image_name


@dataclass
class ImageReference:
    name: str
    namespace: str
    tag: str
    platform: Platforms

    @classmethod
    def parse(cls, image_name: str):
        url, tag = image_name.split(":")

        platform, left_over = get_platform(url)

        namespace, name = split_names(left_over)

        return ImageReference(
            name=name,
            namespace=namespace,
            tag=tag,
            platform=platform
        )

import requests

from datetime import datetime


@dataclass
class TagMetadata:
    name: str
    last_update: datetime
    status: str
    architecture: list[str]


def parse_row(input_json: dict):
    return TagMetadata(
        name=input_json["name"],
        last_update=datetime.fromisoformat(input_json["last_updated"]),
        status=input_json["tag_status"],
        architecture=[version["architecture"] for version in input_json["images"]]
    )

def get_tags(image_reference: ImageReference) -> list[TagMetadata]:
    urls = {
        Platforms.DOCKER: "https://registry.hub.docker.com"
    }

    url = f"{urls.get(image_reference.platform)}/v2/repositories/{image_reference.namespace}/{image_reference.name}/tags/"

    response = requests.get(url)

    return [
        parse_row(input_json=item) for item in response.json()["results"]
    ]

