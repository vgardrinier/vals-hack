#!/bin/bash
# Start Valkyrie runs one by one, never letting the team go above MAX_ACTIVE runs at once.
#
#   DATASET=yaya/precedent@4 TASKS=task-a,task-b scripts/queue_runs.sh runs.txt "agent|model|ENV_VAR secret-name" ...
#
# Appends "<model> <run_id>" to runs.txt for each started run.
# The limit counts every in-progress run in the org (yours and teammates'), not just this script's.
set -u
MAX_ACTIVE=5
out=$1; shift
cd /tmp

active() { valkyrie run list --status in_progress 2>/dev/null | grep -oE "Total: [0-9]+" | grep -oE "[0-9]+" || echo 0; }

for spec in "$@"; do
  IFS='|' read -r agent model secret <<< "$spec"
  while [ "$(active)" -ge "$MAX_ACTIVE" ]; do sleep 30; done
  res=$(valkyrie run start --agent "$agent" --dataset "$DATASET" --task-ids "$TASKS" \
        --model "$model" --provider modal -s $secret --concurrency 2 2>&1)
  id=$(echo "$res" | grep -oE "Run ID: +[a-f0-9-]+" | awk '{print $3}')
  if [ -z "$id" ]; then echo "FAILED $model: $(echo "$res" | tail -2)"; continue; fi
  echo "${model#*/} $id" >> "$out"; echo "started $model $id"
  sleep 10  # let the new run show up as in progress before counting again
done
