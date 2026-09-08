"""Only page selectors and a retry key are accepted from an administrator."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewsOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["refresh", "enhance"]
    requestId: UUID
    source: str | None = Field(default=None, max_length=40)
    topic: str | None = Field(default=None, max_length=40)
    sort: Literal["balanced", "latest"] = "balanced"
    page: int = Field(default=1, ge=1, le=100000)
