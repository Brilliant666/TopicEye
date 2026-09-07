"""Public contracts for Rardar's saved Hotspot News timeline."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl


class _StrictNewsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HotspotNewsSource(_StrictNewsModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=255)
    homepageUrl: HttpUrl
    status: Literal["healthy", "stale", "failed", "not_synced"]
    lastSyncAt: AwareDatetime | None
    itemCount: int = Field(ge=0)
    errorCode: Literal["source_sync_failed"] | None = None


class HotspotNewsItem(_StrictNewsModel):
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=1200)
    sourceKey: str = Field(min_length=1, max_length=40)
    sourceName: str = Field(min_length=1, max_length=255)
    url: HttpUrl
    publishedAt: AwareDatetime | None
    updatedAt: AwareDatetime | None
    fetchedAt: AwareDatetime


class HotspotNewsResponse(_StrictNewsModel):
    status: Literal["ready", "degraded", "stale", "not_synced"]
    syncedAt: AwareDatetime | None
    itemCount: int = Field(ge=0)
    selectedSource: str | None
    sources: list[HotspotNewsSource]
    items: list[HotspotNewsItem]


class HotspotNewsRefreshSourceResult(_StrictNewsModel):
    key: str
    status: Literal["refreshed", "not_modified", "failed", "busy"]
    fetched: int = Field(ge=0)
    created: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    retained: int = Field(ge=0)
    errorCode: Literal["source_sync_failed"] | None = None


class HotspotNewsRefreshResult(_StrictNewsModel):
    status: Literal["completed", "degraded", "busy"]
    startedAt: AwareDatetime
    completedAt: AwareDatetime
    providerCalls: Literal[0] = 0
    sources: list[HotspotNewsRefreshSourceResult]
