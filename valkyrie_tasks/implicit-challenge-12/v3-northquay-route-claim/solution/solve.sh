#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action communicate --field 'subject_id="NQ-204"' --field 'content="18 operational baseline"' --field 'status="published"'
