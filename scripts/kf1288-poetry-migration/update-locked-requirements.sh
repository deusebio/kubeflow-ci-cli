#!/bin/bash

# ensuring Python 3.12 is used:
[[ $(python3 --version) =~ "Python 3.12."[0-9]+ ]] || exit 1

python3 -m venv venv
source venv/bin/activate

pip install tox

tox -e update-requirements

deactivate
rm -rf venv
