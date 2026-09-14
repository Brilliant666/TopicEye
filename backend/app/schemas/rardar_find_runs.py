"""Private, versioned Find result representation."""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas.rardar_product import FindProjectRequest, FindProjectResponse


def restore_find_result(value):
    """Restore the JSON storage representation under the unchanged strict schema."""
    if isinstance(value, dict):
        return FindProjectResponse.model_validate_json(json.dumps(value, ensure_ascii=False))
    return value


FindRunStatus = Literal[
    "created",
    "running",
    "completed",
    "no_candidates",
    "partial",
    "failed",
    "budget_stopped",
    "interrupted",
    "uncertain",
]


class FindRun(BaseModel):
    runId: str
    status: FindRunStatus
    stage: str
    createdAt: datetime
    updatedAt: datetime
    finishedAt: datetime | None
    request: FindProjectRequest
    result: FindProjectResponse | None
    errorCode: str | None
    requestLimit: int
    requestsUsed: int
    schemaVersion: Literal["rardar-find-run-v1"] = "rardar-find-run-v1"

    @field_validator("result", mode="before")
    @classmethod
    def _restore_result(cls, value):
        return restore_find_result(value)


class FindRunSummary(BaseModel):
    runId: str
    status: FindRunStatus
    stage: str
    createdAt: datetime
    updatedAt: datetime
    requirementSummary: str
    repositoryUrl: str | None
    requestsUsed: int


class FindRunList(BaseModel):
    runs: list[FindRunSummary]
