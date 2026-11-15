#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="EG-SUNMESA"' --field 'reviewer="Energy Committee"' --field 'review_type="capacity"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="EG-SUNMESA"' --field 'reviewer="Credit Risk"' --field 'review_type="collateral"'
python3 /app/tools/business_tool.py record --action communicate --field 'subject_id="EG-SUNMESA"' --field 'recipient="SunMesa"' --field 'content="48-hour non-binding extension"'
