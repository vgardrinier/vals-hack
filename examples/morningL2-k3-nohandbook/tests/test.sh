#!/bin/bash
mkdir -p /logs/verifier
python3 /tests/check.py /app/company/finance/invoice_tracker_2026Q4.csv /tests/expected.json > /logs/verifier/check.txt 2>&1
cat /logs/verifier/check.txt
grep -oE '^score=[0-9.]+' /logs/verifier/check.txt | cut -d= -f2 > /logs/verifier/reward.txt
[ -s /logs/verifier/reward.txt ] || echo 0 > /logs/verifier/reward.txt
