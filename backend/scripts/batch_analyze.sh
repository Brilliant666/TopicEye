#!/usr/bin/env bash
set -euo pipefail

# Batch analyze local content items that do not yet have an AI analysis.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

DB_PATH="${DB_PATH:-$BACKEND_DIR/topiceye.db}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
SLEEP_SECONDS="${SLEEP_SECONDS:-3}"

if [[ ! -f "$DB_PATH" ]]; then
    echo "Database not found: $DB_PATH" >&2
    exit 1
fi

IDS=$(sqlite3 "$DB_PATH" "SELECT id FROM content_items WHERE id NOT IN (SELECT content_id FROM ai_analyses) ORDER BY id")

COUNT=0
for ID in $IDS; do
    if [[ -n "${AUTH_TOKEN:-}" ]]; then
        RESULT=$(curl -s -X POST -H "Authorization: Bearer $AUTH_TOKEN" "$BASE_URL/api/v1/analyses/content/$ID" 2>&1 || true)
    else
        RESULT=$(curl -s -X POST "$BASE_URL/api/v1/analyses/content/$ID" 2>&1 || true)
    fi
    if echo "$RESULT" | grep -q "quality_score"; then
        COUNT=$((COUNT + 1))
        echo "[$COUNT] id=$ID OK"
    else
        echo "id=$ID FAILED: $(echo "$RESULT" | head -c 80)"
    fi
    sleep "$SLEEP_SECONDS"
done

echo "Done! Analyzed $COUNT items"
