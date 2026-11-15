#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action schedule_event --field 'subject_id="CW-778"' --field 'start="07:00"' --field 'timezone="America/Los_Angeles"'
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="CW-778"' --field 'field="embargo"' --field 'value="Pacific"'
