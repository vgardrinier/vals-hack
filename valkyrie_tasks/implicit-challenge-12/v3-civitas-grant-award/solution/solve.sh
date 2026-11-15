#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="CIV-26-HL"' --field 'field="award status"' --field 'value="reserved pending"'
python3 /app/tools/business_tool.py record --action create_work_item --field 'subject_id="CIV-26-HL"' --field 'work_type="panel review"' --field 'details="disinterested quorum"'
