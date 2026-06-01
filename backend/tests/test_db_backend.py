from app.core.db_backend import (
    create_database_profile,
    database_backend,
    duckdb_attach_sql,
    duckdb_extension_name,
    sqlite_domain_urls,
    sync_database_url,
)


def test_sqlite_profile_and_duckdb_attach_sql(tmp_path):
    db_path = tmp_path / "topiceye.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    profile = create_database_profile(url)

    assert database_backend(url) == "sqlite"
    assert profile.is_sqlite
    assert profile.sync_url.startswith("sqlite:///")
    assert profile.sqlite_path == str(db_path)
    assert duckdb_extension_name(profile) == "sqlite"
    assert duckdb_attach_sql(profile) == f"ATTACH '{db_path}' AS sqlite_db (TYPE SQLITE, READ_ONLY)"


def test_postgresql_profile_and_duckdb_attach_sql():
    url = "postgresql+asyncpg://topiceye:secret@localhost:5432/topiceye"

    profile = create_database_profile(url)

    assert database_backend(url) == "postgresql"
    assert profile.is_postgresql
    assert sync_database_url(url).startswith("postgresql://")
    assert duckdb_extension_name(profile) == "postgres"
    attach_sql = duckdb_attach_sql(profile)
    assert "TYPE postgres" in attach_sql
    assert "READ_ONLY" in attach_sql
    assert "dbname=topiceye" in attach_sql
    assert "user=topiceye" in attach_sql
    assert "password=secret" in attach_sql


def test_sqlite_domain_urls_are_explicit_opt_in(tmp_path):
    url = "sqlite+aiosqlite:///./topiceye.db"

    default_profile = create_database_profile(url, sqlite_domain_split_enabled=False)
    split_profile = create_database_profile(
        url,
        sqlite_domain_split_enabled=True,
        sqlite_domain_dir=str(tmp_path),
    )

    assert default_profile.sqlite_domain_urls == {}
    assert set(split_profile.sqlite_domain_urls) >= {"content", "topics", "trending", "webnovel", "ops"}
    assert sqlite_domain_urls(url, str(tmp_path))["content"].endswith("topiceye_content.db")
