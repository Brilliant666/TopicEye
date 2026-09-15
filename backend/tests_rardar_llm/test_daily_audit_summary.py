"""Synthetic audit fixtures, real tracker/Text persistence, no production data."""

import asyncio
import json
import socket
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.scheduled_job import JobExecutionLog, ScheduledJob
from app.services import job_tracker
from app.services.daily_audit_summary import MAX_SUMMARY_BYTES, describe_summary, serialize_daily_summary


@pytest_asyncio.fixture
async def tracker_db(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("audit test forbids outbound network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'audit.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: ScheduledJob.__table__.create(c))
        await conn.run_sync(lambda c: JobExecutionLog.__table__.create(c))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(job_tracker, "async_session", factory)
    job_tracker._job_locks.clear()
    yield factory
    await engine.dispose()


def synthetic_result():
    return {
        "status": "partial", "date": "2026-09-15",
        "auditRound": {"schemaVersion": 1, "roundKind": "compensation", "counterScope": "current_invocation",
                       "resumedRound": False, "materials": {"slices": 6, "sliceLimit": 6,
            "round": {"processed": 15, "failedAttempts": 3, "providerRequests": 18},
            "cumulative": {"processed": 23, "failedAttempts": 13, "providerRequests": 28},
            "snapshot": {"reused": 96, "todayPending": 5, "historicalPending": 65,
                         "waitReason": "next_scheduled_pass"},
        }},
        "modules": {"today": {"status": "unchanged", "generationId": "boards-synthetic",
                              "projects": [{"profile": '中文😀"\\' * 1000}] * 100},
                    "historical_review": {"status": "published", "date": "2026-09-15"}},
    }


@pytest.mark.asyncio
async def test_real_track_finish_save_read_preserves_json_and_scopes(tracker_db):
    value = synthetic_result()
    old = json.dumps(value, ensure_ascii=False)[:2000]
    with pytest.raises(ValueError):
        json.loads(old)

    @job_tracker.track_job("rardar_daily_operations")
    async def run():
        return value

    await run()
    row = (await job_tracker.get_recent_logs("rardar_daily_operations"))[0]
    saved = json.loads(row["result_summary"])
    assert row["status"] == "PARTIAL"
    assert saved["status"] == "partial"
    assert saved["auditRound"]["materials"]["round"]["processed"] == 15
    assert saved["auditRound"]["materials"]["cumulative"]["failedAttempts"] == 13
    assert saved["auditRound"]["materials"]["snapshot"]["historicalPending"] == 65
    assert saved["auditRound"]["counterScope"] == "current_invocation"
    assert saved["auditRound"]["resumedRound"] is False
    assert saved["auditRound"]["materials"]["sliceLimit"] == 6
    assert saved["modules"]["historical_review"]["status"] == "published"
    assert "profile" not in row["result_summary"]
    assert len(row["result_summary"].encode()) <= MAX_SUMMARY_BYTES
    assert row["summary_info"]["complete"] is True
    assert (await job_tracker.get_all_job_configs())[0]["last_status"] == "PARTIAL"
    assert not job_tracker._get_job_lock("rardar_daily_operations").locked()


@pytest.mark.asyncio
async def test_legacy_read_is_nonmutating(tracker_db):
    values = ['普通文本😀', '{"status":"partial"}', '{"bad":', '{"x":"' + '中' * 1994]
    async with tracker_db() as db:
        for value in values:
            db.add(JobExecutionLog(job_key="legacy", status="PARTIAL", started_at=datetime.now(UTC),
                                   result_summary=value))
        await db.commit()
    rows = await job_tracker.get_recent_logs("legacy")
    assert {r["result_summary"] for r in rows} == set(values)
    assert all(r["status"] == "PARTIAL" for r in rows)
    assert describe_summary(values[2])["truncationSuspected"] is False
    assert describe_summary(values[3])["truncationSuspected"] is True
    assert await job_tracker.get_recent_logs("legacy") == rows


@pytest.mark.parametrize("status,expected", [("completed", "SUCCESS"), ("partial", "PARTIAL"),
                                             ("failed", "FAILED"), ("skipped", "SKIPPED")])
@pytest.mark.asyncio
async def test_status_mapping_unchanged(tracker_db, status, expected):
    @job_tracker.track_job("rardar_daily_operations")
    async def run():
        return {"status": status}
    await run()
    assert (await job_tracker.get_recent_logs())[0]["status"] == expected


@pytest.mark.asyncio
async def test_audit_write_failure_releases_lease_no_retry(tracker_db, monkeypatch, caplog):
    calls = []
    async def fail(*args, **kwargs):
        raise RuntimeError("secret-must-not-be-logged")
    monkeypatch.setattr(job_tracker, "_finish_log", fail)
    @job_tracker.track_job("rardar_daily_operations")
    async def run():
        calls.append(1)
        return {"status": "partial"}
    with pytest.raises(RuntimeError):
        await run()
    assert calls == [1]
    assert (await job_tracker.get_all_job_configs())[0]["last_status"] == "PARTIAL"
    assert "persistence failed" in caplog.text
    assert "secret-must-not-be-logged" not in caplog.text
    assert not job_tracker._get_job_lock("rardar_daily_operations").locked()


@pytest.mark.asyncio
async def test_timeout_and_cancel_release(tracker_db):
    @job_tracker.track_job("rardar_daily_operations", timeout=0.001)
    async def run():
        await asyncio.sleep(1)
    await run()
    assert (await job_tracker.get_recent_logs())[0]["status"] == "TIMEOUT"
    @job_tracker.track_job("rardar_daily_operations")
    async def cancel():
        raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await cancel()
    assert (await job_tracker.get_recent_logs())[0]["status"] == "INTERRUPTED"
    assert not job_tracker._get_job_lock("rardar_daily_operations").locked()


@pytest.mark.parametrize("text", ['中文😀"\\' * 1000, "x" * 8192, "", "短文"])
def test_unicode_escape_bound_empty_and_omission(text):
    value = synthetic_result()
    value["modules"]["today"]["generationId"] = text
    encoded = serialize_daily_summary(value)
    decoded = json.loads(encoded)
    assert len(encoded.encode("utf-8")) <= MAX_SUMMARY_BYTES
    assert decoded["auditRound"]["materials"]["round"]["providerRequests"] == 18
    assert decoded["limitedValues"] == (1 if len(text) > 160 else 0)
    assert json.loads(serialize_daily_summary({}))["status"] is None


def test_list_samples_keep_total_and_unknown_counters():
    value = synthetic_result()
    value["modules"]["today"]["metadata"] = {"failed": [f"project-{n}" for n in range(100)]}
    saved = json.loads(serialize_daily_summary(value))
    failed = saved["modules"]["today"]["metadata"]["failed"]
    assert failed == {"samples": ["project-0", "project-1"], "totalCount": 100, "omittedCount": 98}
    assert saved["auditRound"]["materials"]["cumulative"]["failedAttempts"] == 13
    empty = json.loads(serialize_daily_summary({"status": "completed"}))
    assert empty["auditRound"] is None
    assert empty["roundMetricsAvailable"] is False


@pytest.mark.asyncio
async def test_new_summary_above_old_character_limit_survives_both_writers(tracker_db):
    value = synthetic_result()
    value["modules"]["today"]["sources"] = [
        {key: "x" * 150 for key in ("source", "status", "errorCode", "generationId", "publishedAt", "sourceDate")}
        for _ in range(2)
    ]
    @job_tracker.track_job("rardar_daily_operations")
    async def run():
        return value
    await run()
    raw = (await job_tracker.get_recent_logs())[0]["result_summary"]
    assert len(raw) > 2000
    assert len(raw.encode()) <= MAX_SUMMARY_BYTES
    assert json.loads(raw)["auditRound"]["materials"]["round"]["processed"] == 15


@pytest.mark.asyncio
async def test_serialization_error_does_not_relabel_or_retry_business(tracker_db, monkeypatch, caplog):
    from app.services import daily_audit_summary
    def fail(*args, **kwargs):
        raise ValueError("private-text")
    monkeypatch.setattr(daily_audit_summary, "serialize_daily_summary", fail)
    calls = []
    @job_tracker.track_job("rardar_daily_operations")
    async def run():
        calls.append(1)
        return {"status": "partial"}
    await run()
    row = (await job_tracker.get_recent_logs())[0]
    assert calls == [1]
    assert row["status"] == "PARTIAL"
    assert json.loads(row["result_summary"])["auditError"] == "serialization_failed"
    assert row["summary_info"]["complete"] is False
    assert "private-text" not in caplog.text
