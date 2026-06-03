from types import SimpleNamespace

import pytest

from app.core import sqlite_retry


class FakeSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))


@pytest.mark.asyncio
async def test_begin_immediate_for_sqlite_uses_database_profile(monkeypatch):
    db = FakeSession()
    monkeypatch.setattr(sqlite_retry, "database_profile", SimpleNamespace(is_sqlite=True))

    await sqlite_retry.begin_immediate_for_sqlite(db)

    assert db.statements == ["BEGIN IMMEDIATE"]


@pytest.mark.asyncio
async def test_begin_immediate_skips_non_sqlite_backends(monkeypatch):
    db = FakeSession()
    monkeypatch.setattr(sqlite_retry, "database_profile", SimpleNamespace(is_sqlite=False))

    await sqlite_retry.begin_immediate_for_sqlite(db)

    assert db.statements == []
