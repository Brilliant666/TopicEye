#!/usr/bin/env python3
"""Test API endpoints via HTTP requests."""
import json
import urllib.request

BASE = "http://localhost:8000"

def fetch(path):
    req = urllib.request.Request(f"{BASE}{path}")
    req.add_header("User-Agent", "test")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

# 1. Health
data = fetch("/health")
print(f"Health: {data}")

# 2. Today picks
data = fetch("/api/v1/contents/today-picks")
print(f"today-picks: items={data['total']}, dup_hidden={data['duplicates_hidden']}, topics={len(data['topics'])}")
if data['items']:
    item = data['items'][0]
    print(f"  First: [{item['id']}] {item['title'][:60]}...")
    a = item.get('analysis', {})
    print(f"  adjusted_curation: {a.get('adjusted_curation_score')}")

# 3. Trends - topics
data = fetch("/api/v1/trends/topics?days=7")
print(f"trends/topics: {len(data['trends'])} trend rows")

# 4. Trends - keywords
data = fetch("/api/v1/trends/keywords?days=7&limit=20")
print(f"trends/keywords: {len(data['keywords'])} keywords")

print("\nAll API tests passed!")
