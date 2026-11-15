#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action create_work_item --field 'subject_id="OW-H77"' --field 'work_type="valuation"' --field 'owner="Valuation"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="OW-H77"' --field 'reviewer="Market Risk"' --field 'review_type="closeout"'
python3 /app/tools/business_tool.py record --action communicate --field 'subject_id="OW-H77"' --field 'recipient="Meridian"' --field 'content="extend non-binding"'
