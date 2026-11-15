#!/bin/bash
# Installs python + the two official SDKs into /opt/plain. Same install for every model.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v curl &> /dev/null || ! command -v python3 &> /dev/null; then
  apt-get update && apt-get install -y curl python3 ca-certificates
fi
curl -LsSf https://astral.sh/uv/install.sh | sh
"$HOME/.local/bin/uv" venv /opt/plain --python 3.12 -q
"$HOME/.local/bin/uv" pip install --python /opt/plain/bin/python -q anthropic openai
mkdir -p /logs
