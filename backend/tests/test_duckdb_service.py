from datetime import datetime, timedelta

import duckdb

from app.core.db_backend import duckdb_attach_sql
from app.services import duckdb_service


def test_duckdb_status_redacts_database_password_on_connection_failure(monkeypatch):
    url = "postgresql+asyncpg://topiceye:s3 cr'et@localhost:5432/topiceye"
    monkeypatch.setattr(duckdb_service.settings, "DATABASE_URL", url)

    analytics = duckdb_service.DuckDBAnalytics()
    attach_sql = duckdb_attach_sql(analytics._profile)

    def fail_get_conn():
        raise RuntimeError(
            f"failed for {url}; conninfo password='s3 cr\\'et'; attach={attach_sql}"
        )

    monkeypatch.setattr(analytics, "_get_conn", fail_get_conn)

    assert analytics.available is False
    status = analytics.status()

    assert status["available"] is False
    assert "s3 cr'et" not in status["error"]
    assert "s3 cr\\'et" not in status["error"]
    assert "password=***" in status["error"]
    assert "postgresql+asyncpg://topiceye:***@localhost:5432/topiceye" in status["error"]


def test_stats_queries_use_latest_analysis_only(monkeypatch):
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE SCHEMA oltp_db")
    conn.execute("""
        CREATE TABLE oltp_db.content_items (
            id INTEGER,
            source_id INTEGER,
            source_name VARCHAR,
            category VARCHAR,
            crawled_at TIMESTAMP,
            duplicate_of INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE oltp_db.sources (
            id INTEGER,
            name VARCHAR,
            source_type VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE oltp_db.ai_analyses (
            id INTEGER,
            content_id INTEGER,
            curation_score DOUBLE,
            created_at TIMESTAMP
        )
    """)

    now = datetime.utcnow()
    conn.execute(
        "INSERT INTO oltp_db.sources VALUES (1, '测试信源', 'RSS')"
    )
    conn.execute(
        "INSERT INTO oltp_db.content_items VALUES (1, 1, '测试信源', 'AI', ?, NULL)",
        [now],
    )
    conn.execute(
        "INSERT INTO oltp_db.ai_analyses VALUES (1, 1, 10.0, ?)",
        [now - timedelta(hours=2)],
    )
    conn.execute(
        "INSERT INTO oltp_db.ai_analyses VALUES (2, 1, 90.0, ?)",
        [now - timedelta(hours=1)],
    )

    analytics = duckdb_service.DuckDBAnalytics()
    monkeypatch.setattr(analytics, "_get_conn", lambda: conn)

    overview = analytics.query_stats_overview(days=7)
    assert overview["total"] == 1
    assert overview["analyzed"] == 1
    assert overview["curated"] == 1
    assert overview["curation_threshold"] == 90.0

    source_distribution = analytics.query_stats_source_distribution(days=7)
    assert source_distribution["sources"] == [
        {
            "source_name": "测试信源",
            "source_type": "rss",
            "content_count": 1,
            "curated_count": 1,
            "curation_rate": 100.0,
        }
    ]

    category_distribution = analytics.query_stats_category_distribution(days=7)
    assert category_distribution["categories"] == [
        {"category": "AI", "content_count": 1, "avg_score": 90.0}
    ]

    daily_trend = analytics.query_stats_daily_trend(days=7)
    assert len(daily_trend["trend"]) == 1
    assert daily_trend["trend"][0]["content_count"] == 1
    assert daily_trend["trend"][0]["curated_count"] == 1
    assert daily_trend["trend"][0]["analyzed_count"] == 1

    conn.close()
