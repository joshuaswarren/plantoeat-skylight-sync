#!/usr/bin/env bash
# Container entrypoint: run the sync on a fixed interval. For one-shot/cron use,
# run `pte-skylight-sync run` directly instead.
set -euo pipefail

interval="${SYNC_INTERVAL:-10800}"   # default 3h
echo "plantoeat-skylight-sync: running every ${interval}s (args: $*)"

while true; do
  if ! pte-skylight-sync run "$@"; then
    echo "sync run failed; will retry next cycle" >&2
  fi
  sleep "${interval}"
done
