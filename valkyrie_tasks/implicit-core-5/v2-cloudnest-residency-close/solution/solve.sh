#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action create_work_item --field 'subject_id="CN-EU44"' --field 'work_type="backup"' --field 'details="snap-188"'
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="CN-EU44"' --field 'field="migration status"' --field 'value="open"'
