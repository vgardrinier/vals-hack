#!/bin/bash
set -euo pipefail
python3 /app/tools/business_tool.py record --action execute_operation --field 'subject_id="BRAMBLE-88"' --field 'operation="scoped deletion"' --field 'details="workspace support backups"'
python3 /app/tools/business_tool.py record --action create_work_item --field 'subject_id="BRAMBLE-88"' --field 'work_type="finance retention export"' --field 'owner="Finance"' --field 'details="FIN-7 segregated remove message excerpt"'
python3 /app/tools/business_tool.py record --action communicate --field 'subject_id="BRAMBLE-88"' --field 'recipient="Bramble"' --field 'content="content deleted limited financial records retained"'
