#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action draft_artifact --field 'subject_id="NL-BR-19"' --field 'artifact_type="revised brochure"' --field 'details="remove hospitalization headline"' --field 'status="draft"'
python3 /app/tools/business_tool.py record --action request_review --field 'subject_id="NL-BR-19"' --field 'reviewer="MLR"' --field 'review_type="promotional"'
