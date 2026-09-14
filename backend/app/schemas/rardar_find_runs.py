"""Private, versioned Find result representation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.rardar_product import FindProjectRequest, FindProjectResponse

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
