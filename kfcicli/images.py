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


from abc import ABC, abstractmethod

class ContainerRegisty(ABC):
    @abstractmethod
    def parse_row(self, input_json: dict) -> TagMetadata:
        pass

    @abstractmethod
    def get_tags(self, image_reference: ImageReference) -> list[TagMetadata]:
        pass

class DockerHub(ContainerRegisty):

    def __init__(self, url="https://registry.hub.docker.com"):
        self.url = url

    def parse_row(self, input_json: dict):
        return TagMetadata(
            name=input_json["name"],
            last_update=datetime.fromisoformat(input_json["last_updated"]),
            status=input_json["tag_status"],
            architecture=[version["architecture"] for version in input_json["images"]]
        )

    def get_tags(self, image_reference: ImageReference) -> list[TagMetadata]:

        url = f"{self.url}/v2/repositories/{image_reference.namespace}/{image_reference.name}/tags/"

        response = requests.get(url)

        return [
            self.parse_row(input_json=item) for item in response.json()["results"]
        ]

class GHCR(ContainerRegisty):

    def __init__(self, token: str, url = "https://api.github.com"):
        self.token = token
        self.url = url

    def parse_row(self, input_json: dict):
        return TagMetadata(
            name=input_json["name"],
            last_update=datetime.fromisoformat(input_json["updated_at"]),
            status="active",
            architecture=["amd64"]
        )

    def get_tags(self, image_reference: ImageReference) -> list[TagMetadata]:

        url = f"{self.url}/orgs/{image_reference.namespace}/packages/container/{image_reference.name}/versions"

        response = requests.get(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })

        return [
            self.parse_row(input_json=item) for item in response.json()
        ]
