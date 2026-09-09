"""The browser supplies only an idempotency key, never sync configuration."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TodayOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: UUID
