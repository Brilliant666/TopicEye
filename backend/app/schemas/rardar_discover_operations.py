from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DiscoverPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: UUID


class DiscoverOperationRequest(DiscoverPrepareRequest):
    planId: UUID
