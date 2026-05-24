#!/usr/bin/env python
import time, sys
sys.path.insert(0, '.')
from app.services.duckdb_service import get_analytics

a = get_analytics()
t = time.time()
r = a.query_dashboard_stats(days=7)
print(f"DuckDB query_dashboard_stats: {time.time()-t:.3f}s")
print(f"  sources: {len(r['source_breakdown'])}, kpi: {r['kpi']}")

t = time.time()
r = a.query_today_picks(hours=48)
print(f"DuckDB query_today_picks: {time.time()-t:.3f}s")
print(f"  items: {len(r)}")