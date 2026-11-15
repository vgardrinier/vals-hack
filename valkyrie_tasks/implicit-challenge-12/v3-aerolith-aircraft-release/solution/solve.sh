#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action create_work_item --field 'subject_id="N721AX"' --field 'work_type="repeat inspection"' --field 'owner="authorized certifier"' --field 'details="fresh release"'
python3 /app/tools/business_tool.py record --action update_record --field 'subject_id="N721AX"' --field 'field="release status"' --field 'value="held pending inspection"'
