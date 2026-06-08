import asyncio

import pytest

from app.services import job_tracker


@pytest.mark.asyncio
async def test_track_job_skips_overlapping_run(monkeypatch):
    calls = {"body": 0, "logs": [], "finished": [], "last": []}
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_upsert(*_args, **_kwargs):
        return None

    async def fake_create_log(job_key: str, trigger_type: str = "scheduler"):
        log_id = len(calls["logs"]) + 1
        calls["logs"].append({"id": log_id, "job_key": job_key, "trigger_type": trigger_type})
        return log_id

    async def fake_finish_log(log_id: int, status: str, result_summary: str = "", error_message: str = "", duration_ms: int = 0):
        calls["finished"].append({
            "id": log_id,
            "status": status,
            "result_summary": result_summary,
            "error_message": error_message,
            "duration_ms": duration_ms,
        })

    async def fake_update_last(job_key: str, status: str):
        calls["last"].append((job_key, status))

    monkeypatch.setattr(job_tracker, "_upsert_job_config", fake_upsert)
    monkeypatch.setattr(job_tracker, "_create_log", fake_create_log)
    monkeypatch.setattr(job_tracker, "_finish_log", fake_finish_log)
    monkeypatch.setattr(job_tracker, "_update_job_last_run", fake_update_last)
    job_tracker._job_locks.pop("overlap_test", None)

    @job_tracker.track_job("overlap_test", name="重叠测试", timeout=5)
    async def tracked_job():
        calls["body"] += 1
        started.set()
        await release.wait()
        return "done"

    first = asyncio.create_task(tracked_job())
    await started.wait()
    second = await tracked_job()
    release.set()
    await first

    assert second is None
    assert calls["body"] == 1
    assert [item["status"] for item in calls["finished"]] == ["SKIPPED", "SUCCESS"]
    assert calls["finished"][0]["result_summary"] == "同一任务仍在运行，本次触发已跳过"
    assert calls["last"] == [("overlap_test", "SKIPPED"), ("overlap_test", "SUCCESS")]
