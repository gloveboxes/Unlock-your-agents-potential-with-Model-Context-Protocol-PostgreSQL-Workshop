!#!/usr/bin/env bash

echo "Preparing the Python environment..."

python -m pip install --upgrade pip

pip install --user -r src/python/workshop/requirements.txt

pip install --user -r requirements-dev.txt

pip install --user -r src/shared/chat/requirements.txt

echo "Python environment setup complete."
