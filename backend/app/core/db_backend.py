"""Database backend configuration helpers.

The app uses SQLAlchemy for OLTP writes and DuckDB for OLAP reads.  Keep the
backend detection here so SQLite/PostgreSQL differences do not leak through the
service layer.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Optional

from sqlalchemy.engine import URL, make_url

DatabaseBackend = Literal["sqlite", "postgresql", "unknown"]


SQLITE_DOMAIN_TABLES: Dict[str, tuple[str, ...]] = {
    "content": (
        "sources",
        "content_items",
        "content_metrics",
        "ai_analyses",
        "ignored_items",
        "user_feedback",
    ),
    "topics": (
        "categories",
        "topic_groups",
        "topic_trends",
        "mother_topics",
        "daily_reports",
        "weekly_digests",
        "monthly_digests",
    ),
    "trending": (
        "trending_items",
        "trending_snapshots",
    ),
    "webnovel": (
        "fanqie_categories",
        "fanqie_books",
        "fanqie_rank_snapshots",
        "qimao_books",
        "zhihu_albums",
        "zhihu_categories",
        "zhihu_rank_snapshots",
    ),
    "ops": (
        "app_settings",
        "notifications",
        "scheduled_jobs",
        "job_execution_logs",
        "llm_models",
        "model_evaluations",
        "llm_call_logs",
    ),
}


@dataclass(frozen=True)
class DatabaseProfile:
    url: str
    backend: DatabaseBackend
    async_driver: Optional[str]
    sync_url: str
    sqlite_path: Optional[str]
    sqlite_domain_urls: Dict[str, str]

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgresql(self) -> bool:
        return self.backend == "postgresql"


def database_backend(url: str) -> DatabaseBackend:
    driver = make_url(url).drivername.split("+", 1)[0]
    if driver == "sqlite":
        return "sqlite"
    if driver in {"postgresql", "postgres"}:
        return "postgresql"
    return "unknown"


def sync_database_url(url: str) -> str:
    parsed = make_url(url)
    backend = database_backend(url)
    if backend == "sqlite":
        return str(parsed.set(drivername="sqlite"))
    if backend == "postgresql":
        return str(parsed.set(drivername="postgresql"))
    return str(parsed)


def sqlite_path_from_url(url: str) -> Optional[str]:
    parsed = make_url(url)
    if database_backend(url) != "sqlite":
        return None
    database = parsed.database
    if database in {None, "", ":memory:"}:
        return database
    return os.path.abspath(database)


def sqlite_domain_urls(base_url: str, domain_dir: str) -> Dict[str, str]:
    """Build SQLite URLs for optional domain split storage.

    This does not activate routing by itself.  It gives future repository-level
    routing a deterministic set of files while keeping single-file SQLite as the
    compatibility default.
    """
    if database_backend(base_url) != "sqlite":
        return {}
    root = Path(domain_dir).expanduser().resolve()
    return {
        domain: f"sqlite+aiosqlite:///{root / f'topiceye_{domain}.db'}"
        for domain in SQLITE_DOMAIN_TABLES
    }


def create_database_profile(
    url: str,
    *,
    sqlite_domain_split_enabled: bool = False,
    sqlite_domain_dir: str = "./data/domains",
) -> DatabaseProfile:
    backend = database_backend(url)
    parsed = make_url(url)
    domain_urls = (
        sqlite_domain_urls(url, sqlite_domain_dir)
        if backend == "sqlite" and sqlite_domain_split_enabled
        else {}
    )
    return DatabaseProfile(
        url=url,
        backend=backend,
        async_driver=parsed.drivername.split("+", 1)[1] if "+" in parsed.drivername else None,
        sync_url=sync_database_url(url),
        sqlite_path=sqlite_path_from_url(url),
        sqlite_domain_urls=domain_urls,
    )


def sqlalchemy_connect_args(profile: DatabaseProfile) -> dict:
    if profile.is_sqlite:
        return {"check_same_thread": False}
    return {}


def database_diagnostics(profile: DatabaseProfile) -> dict:
    """Return a safe database diagnostics payload for health endpoints."""
    analytics = {
        "backend": "duckdb",
        "attach_source": profile.backend,
        "attach_mode": "read_only",
        "extension": None,
    }
    if profile.is_sqlite or profile.is_postgresql:
        analytics["extension"] = duckdb_extension_name(profile)

    return {
        "oltp": {
            "backend": profile.backend,
            "async_driver": profile.async_driver,
            "sync_driver": make_url(profile.sync_url).drivername,
            "sqlite_path": profile.sqlite_path if profile.is_sqlite else None,
            "sqlite_domain_split_enabled": bool(profile.sqlite_domain_urls),
            "sqlite_domain_count": len(profile.sqlite_domain_urls),
        },
        "analytics": analytics,
    }


def redact_database_secrets(message: Optional[str], profile: DatabaseProfile) -> Optional[str]:
    """Remove configured database credentials from diagnostic error text."""
    if message is None:
        return None

    redacted = str(message)
    parsed = make_url(profile.url)

    if parsed.password:
        password_variants = {
            parsed.password,
            _libpq_value(parsed.password),
            _duckdb_sql_literal(_libpq_value(parsed.password)),
        }
        for password in sorted(password_variants, key=len, reverse=True):
            redacted = redacted.replace(password, "***")

    try:
        unsafe_url = parsed.render_as_string(hide_password=False)
        safe_url = parsed.render_as_string(hide_password=True)
        redacted = redacted.replace(unsafe_url, safe_url)
    except Exception:
        pass

    return redacted


def duckdb_attach_sql(profile: DatabaseProfile, *, alias: str = "oltp_db") -> str:
    """Return the DuckDB ATTACH statement for the configured OLTP backend."""
    if profile.is_sqlite:
        if not profile.sqlite_path or profile.sqlite_path == ":memory:":
            raise ValueError("DuckDB analytics requires a file-backed SQLite database")
        path = _duckdb_sql_literal(profile.sqlite_path)
        return f"ATTACH '{path}' AS {alias} (TYPE SQLITE, READ_ONLY)"

    if profile.is_postgresql:
        conninfo = _postgres_conninfo(make_url(profile.url))
        conninfo = _duckdb_sql_literal(conninfo)
        return f"ATTACH '{conninfo}' AS {alias} (TYPE postgres, READ_ONLY)"

    raise ValueError(f"Unsupported DuckDB analytics backend: {profile.backend}")


def duckdb_extension_name(profile: DatabaseProfile) -> str:
    if profile.is_sqlite:
        return "sqlite"
    if profile.is_postgresql:
        return "postgres"
    raise ValueError(f"Unsupported DuckDB analytics backend: {profile.backend}")


def _postgres_conninfo(url: URL) -> str:
    parts = []
    if url.database:
        parts.append(("dbname", url.database))
    if url.username:
        parts.append(("user", url.username))
    if url.password:
        parts.append(("password", url.password))
    if url.host:
        parts.append(("host", url.host))
    if url.port:
        parts.append(("port", str(url.port)))
    for key, value in sorted(url.query.items()):
        if isinstance(value, tuple):
            value = value[-1]
        parts.append((key, str(value)))
    return " ".join(f"{key}={_libpq_value(value)}" for key, value in parts)


def _libpq_value(value: str) -> str:
    if value == "" or any(ch.isspace() or ch in "'\\" for ch in value):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return value


def _duckdb_sql_literal(value: str) -> str:
    return value.replace("'", "''")
