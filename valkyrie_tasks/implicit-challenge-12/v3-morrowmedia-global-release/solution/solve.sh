#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action execute_operation --field 'subject_id="LA-C30"' --field 'operation="replace clip"' --field 'details="HA-1947 MM-BROLL-62"'
python3 /app/tools/business_tool.py record --action stage_artifact --field 'subject_id="LA-C30"' --field 'destination="global"' --field 'details="replacement master"' --field 'status="staged"'
