#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="MC-28"' --field 'review_type="export classification"'
