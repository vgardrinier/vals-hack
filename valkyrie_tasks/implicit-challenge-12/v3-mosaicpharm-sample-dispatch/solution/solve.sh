#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="MP-SMP-604"' --field 'field="shipment status"' --field 'value="compliance hold"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="MP-SMP-604"' --field 'reviewer="Oregon Licensing Services"' --field 'review_type="reinstatement confirmation"'
