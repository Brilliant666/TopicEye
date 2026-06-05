#!/usr/bin/env python3
"""Measure direct DuckDB analytics query latency for local diagnostics."""

from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.duckdb_service import get_analytics


def main() -> None:
    analytics = get_analytics()

    started_at = time.time()
    dashboard = analytics.query_dashboard_stats(days=7)
    print(f"DuckDB query_dashboard_stats: {time.time() - started_at:.3f}s")
    print(f"  sources: {len(dashboard['source_breakdown'])}, kpi: {dashboard['kpi']}")

    started_at = time.time()
    today_picks = analytics.query_today_picks(hours=48)
    print(f"DuckDB query_today_picks: {time.time() - started_at:.3f}s")
    print(f"  items: {len(today_picks)}")


if __name__ == "__main__":
    main()
