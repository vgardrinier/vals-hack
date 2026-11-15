#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="AH-6114"' --field 'field="approved amount"' --field 'value="90,720"'
python3 /app/tools/business_tool.py record --action create_work_item --field 'subject_id="AH-6114"' --field 'work_type="invoice dispute"' --field 'details="4,200 September"'
