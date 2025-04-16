from pathlib import Path
import subprocess

import hcl2

def get_juju_applications_names(filename: Path):
    with open(filename, 'r') as file:
        out = hcl2.load(file)

    for item in out["resource"]:
        for key, value in item["juju_application"].items():
            yield value["charm"][0]["name"]


def set_variable_field(
        variable: str, prop_name: str, prop_value: str,
        filename: Path = 'variables.tf'
):
    with open(filename, 'r') as file:
        out = hcl2.load(file)

    objs = {
        key: value if key != variable else ( value | {prop_name: prop_value} )
        for item in out["variable"]
        for key, value in item.items()
    }

    example = hcl2.Builder()

    for key, value in objs.items():
        example.block("variable", [key], **value)

    example_dict = example.build()
    example_ast = hcl2.reverse_transform(example_dict)

    with open(filename, 'w') as file:
        file.write(hcl2.writes(example_ast))

    subprocess.check_output([
        "sed", '-i', '/type/ s/\"number\"/number/g', str(filename)
    ])

    fix_formatting(filename.parent)


def set_version_field(
        required_version: str | None = None,
        providers_version: dict | None = None,
        filename: Path = 'versions.tf'
):
    with open(filename, 'r') as file:
        out = hcl2.load(file)

    data = out["terraform"][0]

    if required_version:
        data["required_version"] = required_version

    providers_version = providers_version if providers_version else {}

    required_providers = {}
    for provider_dict in data["required_providers"]:
        for key, value in provider_dict.items():
            required_providers |= {
                key: value | {"version": providers_version.get(key, value["version"])}
            }

    data["required_providers"] = required_providers

    example = hcl2.Builder()

    example.block("terraform", [], **data)

    example_dict = example.build()
    example_ast = hcl2.reverse_transform(example_dict)

    with open(filename, 'w') as file:
        file.write(hcl2.writes(example_ast))

    subprocess.check_output([
        "sed", '-i', '/required_providers/ s/=//g', str(filename)
    ])

    fix_formatting(filename.parent)


def fix_formatting(base_dir: Path):

    subprocess.check_call([
        "terraform", "fmt", "-recursive"
    ], cwd=base_dir)


