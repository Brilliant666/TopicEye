"""Public contracts for Rardar's saved Hotspot News timeline."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl


class _StrictNewsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HotspotNewsSource(_StrictNewsModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["official", "media", "community", "aggregate"]
    homepageUrl: HttpUrl
    status: Literal["healthy", "stale", "failed", "not_synced", "paused"]
    lastSyncAt: AwareDatetime | None
    itemCount: int = Field(ge=0)
    errorCode: Literal["source_sync_failed"] | None = None


class HotspotNewsTopic(_StrictNewsModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=40)
    itemCount: int = Field(ge=0)


class HotspotNewsDiscoveryChannel(_StrictNewsModel):
    key: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["official", "media", "community", "aggregate"]
    observedAt: AwareDatetime
    discussionUrl: HttpUrl | None = None
    discussionAt: AwareDatetime | None = None
    rank: int | None = Field(default=None, ge=1)
    points: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)


class HotspotNewsQuickRead(_StrictNewsModel):
    state: Literal["ready", "title_only"]
    titleZh: str = Field(min_length=1, max_length=500)
    summaryZh: str | None = Field(default=None, max_length=600)
    materialKind: Literal["feed_summary", "article_body", "title_only"]
    generatedBy: Literal["ai"] = "ai"
    generatedAt: AwareDatetime


class HotspotNewsItem(_StrictNewsModel):
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=1200)
    sourceKey: str = Field(min_length=1, max_length=40)
    sourceName: str = Field(min_length=1, max_length=255)
    publisherName: str = Field(min_length=1, max_length=255)
    url: HttpUrl
    topicKey: str = Field(min_length=1, max_length=40)
    topicLabel: str = Field(min_length=1, max_length=40)
    contentType: Literal["official_update", "report", "research", "community_discussion", "uncategorized"]
    language: Literal["zh", "en", "unknown"]
    publishedAt: AwareDatetime | None
    updatedAt: AwareDatetime | None
    fetchedAt: AwareDatetime
    discoveryChannels: list[HotspotNewsDiscoveryChannel] = Field(min_length=1)
    quickRead: HotspotNewsQuickRead | None = None


class HotspotNewsResponse(_StrictNewsModel):
    status: Literal["ready", "degraded", "stale", "not_synced"]
    syncedAt: AwareDatetime | None
    itemCount: int = Field(ge=0)
    totalItems: int = Field(ge=0)
    sourceScopeItemCount: int = Field(ge=0)
    topicScopeItemCount: int = Field(ge=0)
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=40)
    totalPages: int = Field(ge=1)
    sort: Literal["balanced", "latest"]
    selectedSource: str | None
    selectedTopic: str | None
    sources: list[HotspotNewsSource]
    topics: list[HotspotNewsTopic]
    items: list[HotspotNewsItem]


class HotspotNewsRefreshSourceResult(_StrictNewsModel):
    key: str
    status: Literal["refreshed", "not_modified", "failed", "busy", "paused"]
    fetched: int = Field(ge=0)
    created: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    retained: int = Field(ge=0)
    errorCode: Literal["source_sync_failed"] | None = None


class HotspotNewsRefreshResult(_StrictNewsModel):
    status: Literal["completed", "degraded", "busy", "paused"]
    startedAt: AwareDatetime
    completedAt: AwareDatetime
    providerCalls: Literal[0] = 0
    sources: list[HotspotNewsRefreshSourceResult]


class HotspotNewsEnhanceItemResult(_StrictNewsModel):
    contentId: int = Field(gt=0)
    sourceKey: str = Field(min_length=1, max_length=40)
    status: Literal["enhanced", "cached", "already_chinese", "failed", "budget_exhausted", "waiting"]
    materialKind: Literal["feed_summary", "article_body", "title_only"] | None = None
    errorCode: str | None = Field(default=None, max_length=80)


class HotspotNewsEnhanceResult(_StrictNewsModel):
    status: Literal["completed", "degraded", "budget_exhausted", "waiting"]
    startedAt: AwareDatetime
    completedAt: AwareDatetime
    considered: int = Field(ge=0)
    enhanced: int = Field(ge=0)
    cacheHits: int = Field(ge=0)
    alreadyChinese: int = Field(ge=0)
    failed: int = Field(ge=0)
    providerCalls: int = Field(ge=0)
    budgetRemaining: int = Field(ge=0)
    items: list[HotspotNewsEnhanceItemResult]
