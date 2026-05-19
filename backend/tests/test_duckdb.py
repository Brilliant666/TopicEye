#!/usr/bin/env python
"""Test DuckDB integration."""
import sys
import os

# Set working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.services.duckdb_service import init_schema, sync_full, query_today_picks, query_topics, query_daily_stats

print("=== init_schema ===")
init_schema()
print("OK")

print("=== sync_full ===")
stats = sync_full()
print("Stats:", stats)

print("=== query_today_picks ===")
picks = query_today_picks()
print(f"Picks: {len(picks)} items")
if picks:
    print("First pick:", picks[0]["title"], "| adj_score:", picks[0].get("adjusted_curation_score"))

print("=== query_topics ===")
topics = query_topics()
print(f"Topics: {len(topics)}")

print("=== query_daily_stats ===")
stats = query_daily_stats()
print("Stats:", stats)

print("ALL OK")
