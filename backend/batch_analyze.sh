#!/bin/bash
# Batch analyze remaining content items
cd /Users/fxbin/Desktop/Project/AIProject/TopicEye/backend

# Get unanalyzed IDs
IDS=$(sqlite3 topiceye.db "SELECT id FROM content_items WHERE id NOT IN (SELECT content_id FROM ai_analyses) ORDER BY id")

COUNT=0
for ID in $IDS; do
    RESULT=$(curl -s -X POST "http://localhost:8000/api/v1/analyses/content/$ID" 2>&1)
    if echo "$RESULT" | grep -q "quality_score"; then
        COUNT=$((COUNT + 1))
        echo "[$COUNT] id=$ID OK"
    else
        echo "id=$ID FAILED: $(echo $RESULT | head -c 80)"
    fi
    sleep 3
done

echo "Done! Analyzed $COUNT items"
