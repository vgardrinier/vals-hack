#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="AQ-417"' --field 'reviewer="disinterested"' --field 'review_type="approval"'
python3 /app/tools/business_tool.py record --action execute_operation --field 'subject_id="AQ-417"' --field 'operation="reservation"' --field 'details="refundable 2,000"'
