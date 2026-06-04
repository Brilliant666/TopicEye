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


def test_dashboard_stats_uses_dynamic_curation_threshold(monkeypatch):
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
    for table_name, timestamp_column in (
        ("fanqie_books", "crawled_at"),
        ("qimao_books", "crawled_at"),
        ("zhihu_albums", "updated_at"),
    ):
        conn.execute(f"""
            CREATE TABLE oltp_db.{table_name} (
                id INTEGER,
                {timestamp_column} TIMESTAMP
            )
        """)

    now = datetime.utcnow()
    conn.execute("INSERT INTO oltp_db.sources VALUES (1, '测试信源', 'RSS')")
    conn.execute("INSERT INTO oltp_db.content_items VALUES (1, 1, '测试信源', 'AI', ?, NULL)", [now])
    conn.execute("INSERT INTO oltp_db.content_items VALUES (2, 1, '测试信源', 'AI', ?, NULL)", [now])
    conn.execute("INSERT INTO oltp_db.ai_analyses VALUES (1, 1, 60.0, ?)", [now])
    conn.execute("INSERT INTO oltp_db.ai_analyses VALUES (2, 2, 90.0, ?)", [now])

    analytics = duckdb_service.DuckDBAnalytics()
    monkeypatch.setattr(analytics, "_get_conn", lambda: conn)

    dashboard = analytics.query_dashboard_stats(days=7)

    assert dashboard["overview"]["curation_threshold"] == 60.0
    assert dashboard["overview"]["curated"] == 2
    assert dashboard["kpi"]["total_curated"] == 2
    assert dashboard["sources"][0]["curated_count"] == 2
    assert dashboard["source_breakdown"][0]["curated_count"] == 2
    assert dashboard["trend"][0]["curated_count"] == 2
    assert dashboard["daily_trend"][0]["curated_count"] == 2

    conn.close()


def test_today_picks_query_uses_latest_analysis_only(monkeypatch):
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE SCHEMA oltp_db")
    conn.execute("""
        CREATE TABLE oltp_db.content_items (
            id INTEGER,
            title VARCHAR,
            url VARCHAR,
            source_id INTEGER,
            source_name VARCHAR,
            source_type VARCHAR,
            platform VARCHAR,
            author VARCHAR,
            published_at TIMESTAMP,
            crawled_at TIMESTAMP,
            content_hash VARCHAR,
            summary VARCHAR,
            raw_content VARCHAR,
            cover_url VARCHAR,
            category VARCHAR,
            tags VARCHAR,
            language VARCHAR,
            status VARCHAR,
            is_favorited BOOLEAN,
            topic_id INTEGER,
            duplicate_of INTEGER,
            similarity_score DOUBLE,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE oltp_db.sources (
            id INTEGER,
            weight INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE oltp_db.ai_analyses (
            id INTEGER,
            content_id INTEGER,
            quality_score DOUBLE,
            hot_score DOUBLE,
            freshness_score DOUBLE,
            creator_score DOUBLE,
            viral_score DOUBLE,
            risk_score DOUBLE,
            curation_score DOUBLE,
            info_density DOUBLE,
            actionability DOUBLE,
            recommended_reason VARCHAR,
            recommendation VARCHAR,
            summary VARCHAR,
            tags VARCHAR,
            enrichment_status VARCHAR,
            enrichment VARCHAR,
            created_at TIMESTAMP
        )
    """)

    now = datetime.utcnow()
    conn.execute("INSERT INTO oltp_db.sources VALUES (1, 5)")
    conn.execute(
        """
        INSERT INTO oltp_db.content_items VALUES (
            1, '最新分析精选', 'https://example.com/pick', 1, '测试信源', 'RSS',
            'rss', NULL, NULL, ?, NULL, '摘要', NULL, NULL, 'AI', '["AI"]',
            'zh', 'analyzed', false, NULL, NULL, 0.0, ?, ?
        )
        """,
        [now, now, now],
    )
    conn.execute(
        """
        INSERT INTO oltp_db.ai_analyses VALUES (
            1, 1, 50, 50, 50, 50, 50, 10, 20, 50, 50,
            '旧理由', '旧推荐', '旧摘要', '["旧"]', 'pending', NULL, ?
        )
        """,
        [now - timedelta(hours=2)],
    )
    conn.execute(
        """
        INSERT INTO oltp_db.ai_analyses VALUES (
            2, 1, 88, 80, 90, 86, 78, 12, 90, 85, 82,
            '新理由', '新推荐', '新摘要', '["新"]', 'pending', NULL, ?
        )
        """,
        [now - timedelta(hours=1)],
    )

    analytics = duckdb_service.DuckDBAnalytics()
    monkeypatch.setattr(analytics, "_get_conn", lambda: conn)

    rows = analytics.query_today_picks(hours=48, curation_threshold=0)

    assert len(rows) == 1
    assert rows[0]["analysis_id"] == 2
    assert rows[0]["curation_score"] == 90.0
    assert rows[0]["recommended_reason"] == "新理由"
    assert rows[0]["adjusted_curation_score"] == 106.0

    conn.close()
