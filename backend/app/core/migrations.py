"""Startup database migration runner.

Replaces the former hand-written SQLite ``ensure_*_schema`` helpers in
``app/main.py``. On startup we bring the database to the latest Alembic
revision:

- Brand-new (empty) database → ``alembic upgrade head`` builds all tables.
- Existing database that predates Alembic (tables present, no
  ``alembic_version`` row) → ``alembic stamp head`` records it as current
  without running DDL, because those databases were already shaped by the old
  ``ensure_*`` helpers.
- Database already under Alembic control → ``alembic upgrade head`` applies
  any pending revisions.

The runner is synchronous on purpose: Alembic's command API is synchronous,
and wrapping it in ``asyncio.to_thread`` keeps the async startup path clean
without contending with the async engine.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.core.db_backend import create_database_profile

logger = logging.getLogger(__name__)

# migrations.py lives in app/core/; backend root is core -> app -> backend.
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _build_alembic_config() -> Config:
    """Build an Alembic Config rooted at the backend directory.

    Startup needs only a script location; constructing the config in memory
    also avoids Alembic's locale-dependent INI reader.  On a Chinese Windows
    host that reader otherwise decodes this UTF-8 file as GBK and prevents the
    application from starting before it can reach PostgreSQL.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(_BACKEND_DIR))
    return cfg


def _alembic_version_table_exists(sync_url: str) -> bool:
    """Return True when the target database already has an alembic_version table."""
    from sqlalchemy import create_engine, inspect

    engine = create_engine(sync_url)
    try:
        return inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()


def _database_has_tables(sync_url: str) -> bool:
    """Return True when the target database already contains application tables.

    Used to distinguish a brand-new empty database (needs ``upgrade head``)
    from a legacy database that predates Alembic (needs ``stamp head``).
    """
    from sqlalchemy import create_engine, inspect

    engine = create_engine(sync_url)
    try:
        existing = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    # Probe for a small set of core tables that have existed since the start.
    probes = {"sources", "content_items", "categories"}
    return bool(existing & probes)


def _stamp_or_upgrade(cfg: Config, *, has_version_table: bool, has_app_tables: bool) -> None:
    """Decide between stamp (legacy DB) and upgrade (new or tracked DB)."""
    if has_version_table:
        logger.info("Database already under Alembic control — running upgrade head")
        command.upgrade(cfg, "head")
        return

    if not has_app_tables:
        logger.info("Empty database detected — running upgrade head to build schema")
        command.upgrade(cfg, "head")
        return

    # Tables exist but no alembic_version row: a legacy DB shaped by the old
    # ensure_* helpers. Stamp it as current so future revisions apply cleanly.
    logger.info(
        "Legacy database detected (tables present, no alembic_version) — "
        "stamping current Alembic head without running DDL"
    )
    command.stamp(cfg, "head")


def _current_db_revision(sync_url: str) -> str | None:
    """Read the version_num currently recorded in alembic_version (None if absent)."""
    from sqlalchemy import create_engine, text

    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _squash_era_schema_present(sync_url: str) -> bool:
    """Probe schema features introduced by the last pre-squash migrations.

    2026-08-18 迁移合并（squash 到单 baseline）后，存量库的 alembic_version
    仍指向旧链 revision。只有 schema 已达到旧链 head（content_event_groups
    表 + content_items.content_type 列，均为合并前最后几个迁移引入）才允许
    自动 stamp 到 baseline；否则拒绝启动，要求先部署合并前版本完成升级。
    """
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(sync_url)
    try:
        if not inspect(engine).has_table("content_event_groups"):
            return False
        with engine.connect() as conn:
            has_content_type = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'content_items' AND column_name = 'content_type'"
                )
            ).scalar()
        return bool(has_content_type)
    finally:
        engine.dispose()


def run_startup_migrations() -> None:
    """Run Alembic migrations to bring the database to the latest revision.

    Safe to call on every startup. No-op side effects when already current.

    On PostgreSQL, acquires a session-level advisory lock (key 1) before
    running upgrade to prevent multiple containers from racing on
    the same migration.
    """
    profile = create_database_profile(settings.DATABASE_URL)
    sync_url = profile.sync_url
    _migration_lock_key = 7103251  # arbitrary constant; all containers share

    cfg = _build_alembic_config()

    try:
        has_version_table = _alembic_version_table_exists(sync_url)
    except Exception as exc:
        logger.warning("Could not inspect database for alembic_version (%s); attempting upgrade head", exc)
        command.upgrade(cfg, "head")
        return

    # 迁移合并兼容：version 表存在但指向不在当前链中的旧 revision（squash
    # 前的链）。schema 特征齐 → stamp 到 baseline；不齐 → 拒绝启动。
    legacy_pointer = False
    if has_version_table:
        from alembic.script import ScriptDirectory

        known_revisions = {rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()}
        current_revision = _current_db_revision(sync_url)
        if current_revision not in known_revisions:
            if _squash_era_schema_present(sync_url):
                logger.warning(
                    "alembic_version points to pre-squash revision %s with squash-era schema present "
                    "— stamping to baseline head (no DDL will run)",
                    current_revision,
                )
                legacy_pointer = True
            else:
                raise RuntimeError(
                    f"alembic_version 指向迁移合并前的 revision {current_revision!r}，且 schema 尚未升级到合并前 head"
                    f"（缺少 content_event_groups / content_items.content_type）。请先用 tag "
                    "`pre-squash-migrations` 对应版本完成数据库升级，再部署本版本。"
                )

    try:
        has_app_tables = _database_has_tables(sync_url) if not has_version_table else True
    except Exception as exc:
        logger.warning("Could not inspect database tables (%s); attempting upgrade head", exc)
        command.upgrade(cfg, "head")
        return

    # PG advisory lock: prevent multi-container concurrent migrations
    pg_lock_conn = None
    if profile.is_postgresql:
        from sqlalchemy import create_engine as _ce

        pg_lock_conn = _ce(sync_url).connect()
        pg_lock_conn.execution_options(autocommit=True)
        pg_lock_conn.execute(__import__("sqlalchemy").text(f"SELECT pg_advisory_lock({_migration_lock_key})"))
    try:
        if legacy_pointer:
            # purge：先清空 alembic_version（旧指针无法被解析成 stamp 路径），
            # 再以 head 重新落指针；不产生任何 DDL。
            command.stamp(cfg, "head", purge=True)
        else:
            _stamp_or_upgrade(cfg, has_version_table=has_version_table, has_app_tables=has_app_tables)
    finally:
        if pg_lock_conn is not None:
            try:
                pg_lock_conn.execute(__import__("sqlalchemy").text(f"SELECT pg_advisory_unlock({_migration_lock_key})"))
                pg_lock_conn.close()
            except Exception:
                pass
