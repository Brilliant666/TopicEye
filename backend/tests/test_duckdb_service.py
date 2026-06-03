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
