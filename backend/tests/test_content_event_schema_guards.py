"""content_event 规范化守卫的数据库级测试。

旧实现（2026-08-18 迁移合并前）在 sqlite 上模拟触发器语义；迁移 squash 到
单一 baseline 后，这里直接在一次性 PostgreSQL 库上验证 baseline 产出的
真实触发器：canonical 与 member 的互斥不变量。
"""

from __future__ import annotations

import glob
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core import migrations as migrations_mod


@pytest.fixture
def guard_db(throwaway_pg_database):
    """Baseline 建好 schema 的一次性 PG 库，返回同步 URL。"""
    migrations_mod.run_startup_migrations()
    return throwaway_pg_database


def _seed(engine):
    now = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, source_type, url, weight, sort_order, status, "
                "fetch_interval_minutes, enabled, hidden, created_at, updated_at) "
                f"VALUES (1, 'S', 'RSS', 'https://t/s', 3, 1, 'active', 60, true, false, '{now}', '{now}')"
            )
        )
        for i in range(1, 6):
            conn.execute(
                text(
                    "INSERT INTO content_items (id, title, url, source_id, content_hash, crawled_at, status, "
                    "is_favorited, created_at, updated_at) "
                    f"VALUES ({i}, 'c{i}', 'https://t/{i}', 1, 'hash{i}', '{now}', 'analyzed', false, "
                    f"'{now}', '{now}')"
                )
            )


def _group(gid: int, canonical: int, policy: str = "earliest") -> str:
    now = datetime.now(UTC).isoformat()
    return (
        f"INSERT INTO content_event_groups (id, canonical_content_id, canonical_policy, "
        f"first_occurrence_at, last_occurrence_at) VALUES ({gid}, {canonical}, '{policy}', '{now}', '{now}')"
    )


def _member(mid: int, gid: int, content: int) -> str:
    return (
        f"INSERT INTO content_event_members (id, event_group_id, content_id, confidence, match_method) "
        f"VALUES ({mid}, {gid}, {content}, 0.9, 'semantic')"
    )


def _expect_integrity_error(conn, stmt: str) -> None:
    # SIM117：两个上下文语义不同（异常断言 + 事务），保持嵌套
    with pytest.raises(IntegrityError), conn.begin():
        conn.execute(text(stmt))


def test_pg_baseline_enforces_canonical_member_disjointness(guard_db):
    engine = create_engine(guard_db)
    try:
        _seed(engine)
        with engine.connect() as conn:
            # 1. canonical 内容不能再作为本组 member
            conn.execute(text(_group(1, 1)))
            conn.commit()
            _expect_integrity_error(conn, _member(1, 1, 1))

            # 2. 已是 member 的内容不能反向成为本组 canonical
            conn.execute(text(_member(2, 1, 2)))
            conn.commit()
            _expect_integrity_error(conn, "UPDATE content_event_groups SET canonical_content_id = 2 WHERE id = 1")

            # 3. 内容身份全局唯一：跨组也不能重复作为 member
            conn.execute(text(_group(2, 3)))
            conn.execute(text(_member(3, 2, 4)))
            conn.commit()
            _expect_integrity_error(conn, _member(4, 2, 1))
            _expect_integrity_error(conn, "UPDATE content_event_members SET content_id = 1 WHERE id = 3")

            # 4. 别组成员不能成为新组的 canonical（same-table 互斥）
            _expect_integrity_error(conn, _group(3, 2))
            _expect_integrity_error(conn, "UPDATE content_event_groups SET canonical_content_id = 2 WHERE id = 2")
    finally:
        engine.dispose()


def test_baseline_ddl_defines_guard_function_and_triggers(guard_db):
    engine = create_engine(guard_db)
    try:
        with engine.connect() as conn:
            func = conn.execute(
                text(
                    "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public' AND p.proname = 'enforce_content_event_canonical_member_disjoint'"
                )
            ).scalar()
            triggers = conn.execute(
                text(
                    "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "WHERE t.tgname IN ('trg_content_event_member_not_canonical', 'trg_content_event_canonical_not_member') "
                    "AND NOT t.tgisinternal"
                )
            ).scalar()
        assert func is not None
        assert triggers == 2
    finally:
        engine.dispose()


def test_baseline_file_documents_noop_downgrade():
    """squash 后 baseline 不支持逐步回滚：downgrade 必须显式 no-op。"""
    path = glob.glob("alembic/versions/*baseline_squash*.py")
    assert len(path) == 1, f"expected exactly one baseline migration, got {path}"
    with open(path[0]) as fp:
        content = fp.read()
    assert "def downgrade() -> None:" in content
    assert "no-op" in content
