"""Durable, fail-closed execution budget for local Rardar Selection runs.

The hash-chained journal is authoritative. A reservation is never refunded,
including after a process dies before dispatch/completion. No prompt, response,
endpoint, credential or provider exception text belongs in this journal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

TASK_ID = "RARDAR-DISCOVER-SHADOW-CONVERGENCE-01"
LIMIT = 40
STAGES = {"negative_control", "scope_value", "meaningful_change", "user_copy", "format_retry"}
_stage: ContextVar[str | None] = ContextVar("rardar_budget_stage", default=None)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


class ProviderBudgetError(RuntimeError):
    def __init__(self, code: str = "provider_budget_invalid"):
        self.code = code
        super().__init__(code)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def plain(path: Path, *, missing: bool = False) -> None:
    """Reject links/reparse points on every component before file access."""
    if not path.is_absolute() or ".." in path.parts:
        raise ProviderBudgetError("provider_budget_unsafe_path")
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise ProviderBudgetError("provider_budget_missing") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProviderBudgetError("provider_budget_unsafe_path")
        if item == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ProviderBudgetError("provider_budget_unsafe_path")


def atomic(path: Path, value: Any) -> None:
    plain(path, missing=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path, *, blocking: bool = True):
    plain(path.parent)
    plain(path, missing=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError:
            raise ProviderBudgetError("provider_budget_busy") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def budget_stage(stage: str):
    if stage not in STAGES:
        raise ProviderBudgetError("provider_budget_stage_invalid")
    token = _stage.set(stage)
    try:
        yield
    finally:
        _stage.reset(token)


class ProviderBudgetLedger:
    def __init__(self, path: Path, run_id: str):
        if not _SAFE_ID.fullmatch(run_id):
            raise ProviderBudgetError("provider_budget_run_invalid")
        self.path = path
        self.run_id = run_id
        self.events = path.with_name("provider-budget-events.jsonl")
        self.lock = path.with_name("provider-budget.lock")

    @classmethod
    def initialize(cls, path: Path, run_id: str) -> ProviderBudgetLedger:
        """Explicit operator action only; child execution never calls this."""
        ledger = cls(path, run_id)
        plain(path.parent, missing=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        registry = path.parent.parent / "shadow-convergence-budget-registration.json"
        with file_lock(registry.with_suffix(".lock")):
            if registry.exists() or path.exists() or ledger.events.exists():
                raise ProviderBudgetError("provider_budget_already_initialized")
            atomic(registry, {"taskId": TASK_ID, "runId": run_id, "path": str(path)})
            event = {
                "sequence": 1,
                "runId": run_id,
                "taskId": TASK_ID,
                "kind": "created",
                "at": _now(),
                "limit": LIMIT,
                "previousDigest": None,
            }
            event["digest"] = digest(event)
            with ledger.events.open("xb") as handle:
                handle.write(canonical(event))
                handle.flush()
                os.fsync(handle.fileno())
            atomic(path, ledger._replay()[0])
        return ledger

    def _replay(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        plain(self.events)
        raw = self.events.read_bytes()
        if len(raw) > 2_000_000 or not raw.endswith(b"\n"):
            raise ProviderBudgetError()
        try:
            events = [json.loads(line) for line in raw.splitlines()]
            if not events or events[0].get("kind") != "created" or events[0].get("limit") != LIMIT:
                raise ValueError()
            previous = None
            attempts: dict[str, dict[str, Any]] = {}
            hits = 0
            for index, event in enumerate(events, 1):
                claimed = event["digest"]
                if (
                    event["sequence"] != index
                    or event["previousDigest"] != previous
                    or event["runId"] != self.run_id
                    or event["taskId"] != TASK_ID
                    or claimed != digest({key: value for key, value in event.items() if key != "digest"})
                ):
                    raise ValueError()
                previous = claimed
                kind = event["kind"]
                if kind == "created":
                    if index != 1:
                        raise ValueError()
                    continue
                if event["stage"] not in STAGES:
                    raise ValueError()
                identifier = event.get("attemptId")
                if kind == "cache_hit":
                    hits += 1
                elif kind == "reserved":
                    if identifier in attempts or len(attempts) >= LIMIT:
                        raise ValueError()
                    attempts[identifier] = {"stage": event["stage"], "dispatched": False, "outcome": None}
                elif kind in {"dispatched", "succeeded", "failed"}:
                    attempt = attempts[identifier]
                    if attempt["stage"] != event["stage"] or attempt["outcome"] is not None:
                        raise ValueError()
                    if kind == "dispatched":
                        if attempt["dispatched"]:
                            raise ValueError()
                        attempt["dispatched"] = True
                    else:
                        if not attempt["dispatched"]:
                            raise ValueError()
                        attempt["outcome"] = kind
                else:
                    raise ValueError()
            summary = {
                "schemaVersion": 1,
                "runId": self.run_id,
                "taskId": TASK_ID,
                "createdAt": events[0]["at"],
                "updatedAt": events[-1]["at"],
                "limit": LIMIT,
                "reserved": len(attempts),
                "attempted": sum(a["dispatched"] for a in attempts.values()),
                "completed": sum(a["outcome"] is not None for a in attempts.values()),
                "succeeded": sum(a["outcome"] == "succeeded" for a in attempts.values()),
                "failed": sum(a["outcome"] == "failed" for a in attempts.values()),
                "cacheHits": hits,
                "remaining": LIMIT - len(attempts),
                "stageBreakdown": {
                    stage: sum(a["stage"] == stage for a in attempts.values()) for stage in sorted(STAGES)
                },
                "lastAttemptId": next(reversed(attempts), None),
                "journalDigest": previous,
            }
            summary["digest"] = digest(summary)
            return summary, events
        except (KeyError, ValueError, TypeError):
            raise ProviderBudgetError() from None

    def _read(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        plain(self.path)
        registry = self.path.parent.parent / "shadow-convergence-budget-registration.json"
        plain(registry)
        try:
            if json.loads(registry.read_bytes()) != {"taskId": TASK_ID, "runId": self.run_id, "path": str(self.path)}:
                raise ValueError()
            saved = json.loads(self.path.read_bytes())
            if saved.get("digest") != digest({key: value for key, value in saved.items() if key != "digest"}):
                raise ValueError()
            summary, events = self._replay()
            if saved["journalDigest"] not in {event["digest"] for event in events}:
                raise ValueError()
            # A valid journal tail survives a crash before atomic snapshot replacement.
            return summary, events
        except (KeyError, ValueError, TypeError):
            raise ProviderBudgetError() from None

    def snapshot(self) -> dict[str, Any]:
        with file_lock(self.lock):
            return self._read()[0]

    def record(self, kind: str, stage: str, attempt_id: str | None = None) -> str | None:
        if stage not in STAGES:
            raise ProviderBudgetError("provider_budget_stage_invalid")
        with file_lock(self.lock):
            summary, events = self._read()
            if kind == "reserved":
                if summary["remaining"] <= 0:
                    raise ProviderBudgetError("provider_budget_exhausted")
                if stage == "negative_control" and summary["stageBreakdown"][stage] >= 6:
                    raise ProviderBudgetError("provider_budget_negative_control_exhausted")
                attempt_id = uuid4().hex
            event = {
                "sequence": len(events) + 1,
                "runId": self.run_id,
                "taskId": TASK_ID,
                "kind": kind,
                "at": _now(),
                "stage": stage,
                "attemptId": attempt_id,
                "previousDigest": events[-1]["digest"],
            }
            event["digest"] = digest(event)
            with self.events.open("ab") as handle:
                handle.write(canonical(event))
                handle.flush()
                os.fsync(handle.fileno())
            atomic(self.path, self._replay()[0])
        return attempt_id

    @contextmanager
    def execution(self, stage: str):
        # Cross-process concurrency=1, independently of TopicEye's route pool.
        with file_lock(self.path.with_name("provider-execution.lock"), blocking=False):
            identifier = self.record("reserved", stage)
            self.record("dispatched", stage, identifier)
            try:
                yield identifier
            except BaseException:
                self.record("failed", stage, identifier)
                raise
            else:
                self.record("succeeded", stage, identifier)


def execution_budget(scene: str) -> tuple[ProviderBudgetLedger, str] | None:
    """Selection requires a ledger. With one attached, all Rardar calls share it."""
    guarded = scene.startswith("rardar_worth_seeing_")
    configured = any(
        os.environ.get(name) for name in ("RARDAR_LLM_RUN_ID", "RARDAR_LLM_BUDGET_PATH", "RARDAR_LLM_BUDGET_LIMIT")
    )
    if not guarded and not (configured and scene.startswith("rardar_")):
        return None
    run_id = os.environ.get("RARDAR_LLM_RUN_ID", "")
    path = os.environ.get("RARDAR_LLM_BUDGET_PATH", "")
    if not run_id or not path or os.environ.get("RARDAR_LLM_BUDGET_LIMIT") != str(LIMIT):
        raise ProviderBudgetError("provider_budget_missing")
    stages = {
        "rardar_worth_seeing_gate": "scope_value",
        "rardar_worth_seeing_meaningful_change": "meaningful_change",
        "rardar_worth_seeing_copy": "user_copy",
    }
    if scene not in stages:
        raise ProviderBudgetError("provider_budget_scene_forbidden")
    ledger = ProviderBudgetLedger(Path(path), run_id)
    ledger.snapshot()
    return ledger, _stage.get() or stages[scene]
