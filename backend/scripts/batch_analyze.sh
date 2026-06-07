#!/usr/bin/env bash
set -euo pipefail

# Batch analyze pending content through the HTTP API.
#
# This intentionally does not read topiceye.db directly. The backend owns the
# active database profile, so the same script works for SQLite and PostgreSQL.
BASE_URL="${BASE_URL:-http://localhost:8000}"
LIMIT="${LIMIT:-20}"
HOURS="${HOURS:-}"
MAX_ROUNDS="${MAX_ROUNDS:-50}"
SLEEP_SECONDS="${SLEEP_SECONDS:-3}"

if [[ -z "${AUTH_TOKEN:-}" ]]; then
    echo "AUTH_TOKEN is required because /api/v1/analyses/pending requires login." >&2
    exit 1
fi

TOTAL_ANALYZED=0
for ROUND in $(seq 1 "$MAX_ROUNDS"); do
    QUERY="limit=$LIMIT&sync=true"
    if [[ -n "$HOURS" ]]; then
        QUERY="$QUERY&hours=$HOURS"
    fi

    BODY=$(curl -fsS -X POST \
        -H "Authorization: Bearer $AUTH_TOKEN" \
        "$BASE_URL/api/v1/analyses/pending?$QUERY")

    COUNT=$(python -c 'import json,sys; payload=json.load(sys.stdin); print(int(payload.get("count", 0)))' <<< "$BODY")
    IDS=$(python -c 'import json,sys; payload=json.load(sys.stdin); ids=payload.get("analyzed_ids") or payload.get("queued_ids") or payload.get("ids") or []; print(",".join(map(str, ids)))' <<< "$BODY")
    MESSAGE=$(python -c 'import json,sys; payload=json.load(sys.stdin); print(payload.get("message", ""))' <<< "$BODY")

    if [[ "$COUNT" -eq 0 ]]; then
        echo "No pending content remains. $MESSAGE"
        break
    fi

    TOTAL_ANALYZED=$((TOTAL_ANALYZED + COUNT))
    echo "[$ROUND] analyzed=$COUNT ids=${IDS:-none}"
    sleep "$SLEEP_SECONDS"
done

echo "Done! Analyzed $TOTAL_ANALYZED items"
