from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntegrationStatusResponse(BaseModel):
    provider: str
    configured: bool
    api_key_hint: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    sync_endpoint_configured: bool = False
    install_command: Optional[str] = None
    docs_url: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None


class IntegrationUpdateRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)
    config: dict[str, Any] = Field(default_factory=dict)


class WeReadSyncResponse(BaseModel):
    fetched: int
    new: int
    duplicates: int
    message: str
    source_name: str
