#!/bin/bash

PATH=$PATH:/home/deusebio/.pyenv/bin

PYTHON_VERSION=$(python --version)

# Check that Python used is at version 3.12
[[ "$PYTHON_VERSION" =~ "Python 3.12."[0-9]+ ]] || exit 1

echo "Creating env..."

python -m venv my-env
source my-env/bin/activate

echo "Update envs..."

pip install tox
tox -e update-requirements

echo "Cleanup"
rm -rf my-env