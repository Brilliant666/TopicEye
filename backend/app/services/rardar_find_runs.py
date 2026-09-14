"""Small durable synchronous runs. No background paid resume or second ledger."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.core.database import async_session
from app.repositories.rardar_find_run_repo import FindRunRepository
from app.schemas.rardar_product import FindProjectRequest
from app.services.llm.daily_provider_budget import daily_budget_status
from app.services.llm.find_operation import find_operation
from app.services.llm.provider_budget import ProviderBudgetError
from app.services.rardar_product import find_projects


class FindRunError(Exception):
    def __init__(self, code: str, status_code: int = 409):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def _utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def _effective(row):
    status = row.status if hasattr(row, "status") else row["status"]
    deadline = row.execution_deadline if hasattr(row, "execution_deadline") else row["execution_deadline"]
    used = row.requests_used if hasattr(row, "requests_used") else row["requests_used"]
    if status == "running" and deadline and _utc(deadline) <= datetime.now(UTC):
        return "uncertain" if used else "interrupted"
    return status


def _view(row):
    status = _effective(row)
    return {
        "runId": row.run_id,
        "status": status,
        "stage": "execution_expired" if status != row.status else row.stage,
        "createdAt": _utc(row.created_at),
        "updatedAt": _utc(row.updated_at),
        "finishedAt": _utc(row.execution_deadline if status != row.status else row.finished_at),
        "request": row.request_payload,
        "result": row.result_payload,
        "errorCode": "find_execution_interrupted" if status != row.status else row.error_code,
        "requestLimit": row.request_limit,
        "requestsUsed": row.requests_used,
        "schemaVersion": row.result_schema_version,
    }


class FindRunService:
    def __init__(self, session_factory=async_session, config=settings, runner=find_projects):
        self.sessions = session_factory
        self.config = config
        self.runner = runner

    async def create(self, user_id: int, payload: FindProjectRequest, key: str, request_limit=None):
        # The optional lower limit is a trusted operator/test input, never an API field.
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            raise FindRunError("find_idempotency_key_invalid", 422)
        body = payload.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        async with self.sessions() as db:
            repo = FindRunRepository(db)
            existing = await repo.by_key(user_id, key)
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise FindRunError("find_idempotency_conflict")
                return _view(existing)
            cap = self.config.RARDAR_FIND_RUN_REQUEST_LIMIT
            if request_limit is not None:
                cap = min(cap, max(0, request_limit))
            if self.config.RARDAR_DAILY_OPERATIONS_ENABLED:
                budget = await daily_budget_status(db)
                cap = min(cap, budget["remaining"] if budget["configured"] else 0)
            try:
                row = await repo.add(
                    run_id=str(uuid4()),
                    user_id=user_id,
                    idempotency_key=key,
                    request_fingerprint=fingerprint,
                    request_payload=body,
                    requirement_summary=payload.requirement[:160],
                    repository_url=payload.repositoryUrl,
                    request_limit=cap,
                    audit_metadata={
                        "accounting": "reserved_before_http",
                        "attempts": [],
                        "planPrompt": "rardar-find-plan-v2",
                        "planSchema": "rardar-find-plan-schema-v2",
                        "comparisonPrompt": "rardar-find-project-v5",
                        "comparisonSchema": "rardar-find-project-schema-v3",
                    },
                )
                await db.commit()
                return _view(row)
            except IntegrityError:
                await db.rollback()
                existing = await repo.by_key(user_id, key)
                if existing is None:
                    raise FindRunError("find_run_save_failed", 503) from None
                if existing.request_fingerprint != fingerprint:
                    raise FindRunError("find_idempotency_conflict") from None
                return _view(existing)
            except SQLAlchemyError:
                with suppress(SQLAlchemyError):
                    await db.rollback()
                raise FindRunError("find_run_save_failed", 503) from None

    async def get(self, user_id: int, run_id: str):
        async with self.sessions() as db:
            row = await FindRunRepository(db).get(user_id, run_id)
            if row is None:
                raise FindRunError("find_run_not_found", 404)
            return _view(row)

    async def by_key(self, user_id: int, key: str):
        async with self.sessions() as db:
            row = await FindRunRepository(db).by_key(user_id, key)
            if row is None:
                raise FindRunError("find_run_not_found", 404)
            return _view(row)

    async def recent(self, user_id: int, limit: int = 20):
        async with self.sessions() as db:
            rows = await FindRunRepository(db).recent(user_id, min(50, max(1, limit)))
            return {
                "runs": [
                    {
                        "runId": r["run_id"],
                        "status": _effective(r),
                        "stage": "execution_expired" if _effective(r) != r["status"] else r["stage"],
                        "createdAt": _utc(r["created_at"]),
                        "updatedAt": _utc(r["updated_at"]),
                        "requirementSummary": r["requirement_summary"],
                        "repositoryUrl": r["repository_url"],
                        "requestsUsed": r["requests_used"],
                    }
                    for r in rows
                ]
            }

    async def execute(self, user_id: int, run_id: str):
        current = await self.get(user_id, run_id)
        if current["status"] != "created":
            return current
        token = str(uuid4())
        # Covers finite stage retries; expiry is never permission to dispatch again.
        seconds = min(1800, 120 + 180 * max(1, current["requestLimit"]))
        deadline = datetime.now(UTC) + timedelta(seconds=seconds)
        async with self.sessions() as db:
            claimed = await FindRunRepository(db).claim(user_id, run_id, token, deadline)
            await db.commit()
        if not claimed:
            return await self.get(user_id, run_id)

        async def checkpoint(stage, result=None):
            values = {"stage": stage}
            if result is not None:
                values["result_payload"] = result.model_dump(mode="json")
            async with self.sessions() as db:
                if not await FindRunRepository(db).checkpoint(run_id, token, **values):
                    raise FindRunError("find_execution_ownership_lost")
                await db.commit()

        async def reserve(metadata):
            async with self.sessions() as db:
                repo = FindRunRepository(db)
                row = await repo.get(user_id, run_id)
                if row is None:
                    raise ProviderBudgetError("find_run_reservation_failed")
                audit = dict(row.audit_metadata)
                audit["attempts"] = [*audit.get("attempts", []), metadata]
                if not await repo.reserve(run_id, token, audit):
                    raise ProviderBudgetError("find_run_request_limit")
                await db.commit()

        async def finish(status, code, result=None, transport=None):
            values = {"status": status, "stage": "finished", "error_code": code, "finished_at": datetime.now(UTC)}
            if result is not None:
                values["result_payload"] = result.model_dump(mode="json")
            async with self.sessions() as db:
                repo = FindRunRepository(db)
                row = await repo.get(user_id, run_id)
                if row and transport:
                    values["audit_metadata"] = {**row.audit_metadata, "transport": transport}
                if not await repo.checkpoint(run_id, token, **values):
                    raise FindRunError("find_execution_ownership_lost")
                await db.commit()

        with find_operation(run_id=run_id, request_limit=current["requestLimit"], reserve=reserve) as state:
            try:
                async with asyncio.timeout(seconds):
                    result = await self.runner(
                        FindProjectRequest.model_validate(current["request"]),
                        config=self.config,
                        operation_id=run_id,
                        progress=checkpoint,
                    )
                code = result.errorCode
                if result.aiState == "ready":
                    status = "completed"
                elif result.aiState == "insufficient_candidates":
                    status = "no_candidates"
                elif code and any(word in code for word in ("budget", "request_limit")):
                    status = "budget_stopped"
                elif state.dispatched > state.completed + state.known_failed:
                    status = "uncertain"
                else:
                    status = "partial" if result.quickCandidates else "failed"
            except (asyncio.CancelledError, TimeoutError) as error:
                status = "uncertain" if state.dispatched > state.completed + state.known_failed else "interrupted"
                with suppress(Exception):
                    await asyncio.shield(finish(status, "find_execution_interrupted"))
                # The persisted lease still expires if saving failed; never report saved success.
                if isinstance(error, asyncio.CancelledError):
                    raise
                return await self.get(user_id, run_id)
            except Exception as error:
                code = error.code if isinstance(error, FindRunError | ProviderBudgetError) else "find_execution_failed"
                status = "budget_stopped" if "budget" in code or "request_limit" in code else "failed"
                if state.dispatched > state.completed + state.known_failed:
                    status = "uncertain"
                result = None
            try:
                await finish(
                    status,
                    code,
                    result,
                    {
                        "dispatched": state.dispatched,
                        "completed": state.completed,
                        "failed": state.failed,
                        "knownFailed": state.known_failed,
                    },
                )
            except Exception:
                raise FindRunError("find_result_save_failed", 503) from None
        return await self.get(user_id, run_id)


service = FindRunService()
