#!/bin/bash
# Downloads the Redwood Inference company docs (EnterpriseRAG-Bench, MIT) used as background noise.
# Usage: gen/fetch_redwood.sh ../ext/redwood
set -euo pipefail
dest=${1:-../ext/redwood}
mkdir -p "$dest"
for s in gmail_slice_0001 slack_slice_0001 jira_slice_0001; do
  gh release download --repo onyx-dot-app/EnterpriseRAG-Bench -p "$s.zip" -D "$dest" --clobber
  unzip -oq "$dest/$s.zip" -d "$dest/$s"
done
