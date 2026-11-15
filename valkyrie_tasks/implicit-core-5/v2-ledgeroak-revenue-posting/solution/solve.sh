#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="LO-71"' --field 'field="technical completion"' --field 'value="complete"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="LO-71"' --field 'review_type="acceptance"' --field 'reviewer="Kira Bowen"'
