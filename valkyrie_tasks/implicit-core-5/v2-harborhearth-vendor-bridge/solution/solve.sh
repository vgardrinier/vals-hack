#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action draft_artifact --field 'subject_id="GuestPulse"' --field 'artifact_type="bridge"' --field 'details="30 ingestion read-only termination no new"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="guestpulse"' --field 'reviewer="Security"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="guestpulse"' --field 'reviewer="Enterprise Risk"'
