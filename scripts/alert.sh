#!/usr/bin/env bash
# Opens or updates a single "pipeline-alert" issue when a run fails, and closes it on recovery.
set -euo pipefail
mode="$1"
label="pipeline-alert"
run_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
open_issue=$(gh issue list --label "$label" --state open --json number -q '.[0].number' 2>/dev/null || true)

if [ "$mode" = "failed" ]; then
  gh label create "$label" --color B60205 --description "Automated pipeline failure alert" --force >/dev/null
  details="(no summary: the run failed before the pipeline recorded one)"
  if [ -f summary.json ]; then
    details=$(jq -r '"run_id: \(.run_id)\nstatus: \(.status)\nfailed checks: \(.failed_checks | join(", "))\nanomaly injected: \(.anomaly // "none")\nerror: \(.error // "none")"' summary.json)
  fi
  body=$(printf 'Run %s failed at %s.\n\n```\n%s\n```\n' "$run_url" "$(date -u +%FT%TZ)" "$details")
  if [ -z "$open_issue" ]; then
    gh issue create --title "Pipeline run failing" --label "$label" --body "$body"
  else
    gh issue comment "$open_issue" --body "$body"
  fi
elif [ "$mode" = "recovered" ] && [ -n "$open_issue" ]; then
  gh issue comment "$open_issue" --body "Recovered: run $run_url succeeded at $(date -u +%FT%TZ)."
  gh issue close "$open_issue"
fi
