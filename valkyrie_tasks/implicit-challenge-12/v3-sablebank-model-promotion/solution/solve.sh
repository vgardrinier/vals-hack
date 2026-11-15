#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action configure_system --field 'subject_id="SB-MODEL-4.2"' --field 'setting="mode"' --field 'value="shadow"'
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="SB-MODEL"' --field 'field="champion"' --field 'value="4.1"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="SB-MODEL-4.2"' --field 'reviewer="Model Risk"' --field 'review_type="proxy"'
