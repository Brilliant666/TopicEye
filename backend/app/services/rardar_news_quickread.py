"""Optional, evidence-bound Chinese reading aids for saved Rardar news."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem
from app.repositories.rardar_hotspot_news_repo import RardarHotspotNewsRepository
from app.schemas.rardar_hotspot_news import HotspotNewsEnhanceItemResult, HotspotNewsEnhanceResult
from app.services.article_reader import ArticleReaderError, read_or_create_snapshot
from app.services.llm.provider_budget import ProviderBudgetError, execution_budget
from app.services.rardar_hotspot_news import _text_digest, load_hotspot_news
from app.services.rardar_llm_control import (
    RardarLLMError,
    RardarLLMMetadata,
    RardarLLMScene,
    RardarStructuredResult,
    ReasoningEffort,
    call_rardar_structured,
    resolve_rardar_route_identity,
)
from app.services.rardar_news_operation_lock import news_writer

QUICK_READ_MARKER = "rardarHotspotNewsQuickRead"
QUICK_READ_FAILURE_MARKER = "rardarHotspotNewsQuickReadFailure"
QUICK_READ_VERSION = 1
QUICK_READ_PROMPT_VERSION = "rardar-news-quickread-v1"
QUICK_READ_SCHEMA_VERSION = "rardar-news-quickread-output-v1"
QUICK_READ_TASK_ID = "RARDAR-NEWS-CHINESE-QUICKREAD-01"
_HAN = re.compile(r"[\u3400-\u9fff]")


class _QuickReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    titleZh: str = Field(min_length=1, max_length=500)
    summaryZh: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def contains_chinese(self) -> _QuickReadOutput:
        if not _HAN.search(self.titleZh):
            raise ValueError("titleZh must contain Chinese")
        if self.summaryZh is not None and not _HAN.search(self.summaryZh):
            raise ValueError("summaryZh must contain Chinese")
        return self


@dataclass(frozen=True)
class _Material:
    kind: Literal["feed_summary", "article_body", "title_only"]
    text: str | None
    digest: str


StructuredCaller = Callable[..., Awaitable[RardarStructuredResult[_QuickReadOutput]]]
RouteResolver = Callable[[], Awaitable[str]]
MaterialLoader = Callable[[AsyncSession, ContentItem, str], Awaitable[_Material]]


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _already_readable_chinese(item: ContentItem, language: str) -> bool:
    title = item.title or ""
    summary = item.summary or ""
    return language == "zh" and bool(_HAN.search(title)) and (not summary or bool(_HAN.search(summary)))


def _native_hn_post(item: ContentItem) -> bool:
    return (urlsplit(item.url).hostname or "").lower().rstrip(".") == "news.ycombinator.com"


async def _load_material(db: AsyncSession, item: ContentItem, source_key: str) -> _Material:
    if item.summary and item.summary.strip():
        text = item.summary.strip()
        return _Material("feed_summary", text, hashlib.sha256(text.encode("utf-8")).hexdigest())
    if source_key != "hacker-news" or _native_hn_post(item):
        return _Material("title_only", None, _text_digest(item.title))
    try:
        snapshot, _ = await read_or_create_snapshot(db, item)
    except (ArticleReaderError, httpx.RequestError):
        return _Material("title_only", None, _text_digest(item.title))
    body = (snapshot.text_content or "").strip()[:6000]
    if len(body) < 60:
        return _Material("title_only", None, _text_digest(item.title))
    return _Material("article_body", body, snapshot.content_hash)


def _identity(item: ContentItem, material: _Material, route_identity: str) -> str:
    return _canonical_digest(
        {
            "version": QUICK_READ_VERSION,
            "promptVersion": QUICK_READ_PROMPT_VERSION,
            "schemaVersion": QUICK_READ_SCHEMA_VERSION,
            "routeIdentity": route_identity,
            "sourceTitleSha256": _text_digest(item.title),
            "sourceSummarySha256": _text_digest(item.summary),
            "materialKind": material.kind,
            "materialSha256": material.digest,
        }
    )


def _current_marker(item: ContentItem, *, identity: str) -> dict[str, Any] | None:
    tags = item.tags if isinstance(item.tags, dict) else {}
    marker = tags.get(QUICK_READ_MARKER)
    if not isinstance(marker, dict) or marker.get("version") != QUICK_READ_VERSION:
        return None
    if marker.get("inputIdentity") != identity:
        return None
    if marker.get("sourceTitleSha256") != _text_digest(item.title) or marker.get("sourceSummarySha256") != _text_digest(
        item.summary
    ):
        return None
    state = marker.get("state")
    summary = marker.get("summaryZh")
    if state == "title_only" and summary is not None:
        return None
    if state not in {"ready", "title_only"} or not isinstance(marker.get("titleZh"), str):
        return None
    return marker


def _messages(item: ContentItem, material: _Material) -> list[dict[str, Any]]:
    material_contract = (
        "Only the original title is available. Translate it faithfully. summaryZh MUST be null."
        if material.kind == "title_only"
        else "Write one to three concise Chinese sentences based only on MATERIAL. Preserve attribution and uncertainty."
    )
    user_payload = {
        "originalTitle": item.title,
        "materialKind": material.kind,
        "material": material.text,
    }
    return [
        {
            "role": "system",
            "content": (
                "You create a faithful Chinese reading aid for one saved technology-news item. "
                "Never add facts, numbers, dates, capabilities, causes or conclusions absent from the supplied material. "
                "Keep phrases such as 'the company announced', 'the author argues', and 'the report says'. "
                "Hacker News rank, score, comments and discussion are not article evidence. "
                f"{material_contract} Return strict JSON with exactly titleZh and summaryZh."
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))},
    ]


def _save_success(
    item: ContentItem,
    *,
    output: _QuickReadOutput,
    material: _Material,
    identity: str,
    route_identity: str,
    metadata: RardarLLMMetadata,
) -> None:
    if material.kind == "title_only" and output.summaryZh is not None:
        raise RardarLLMError("rardar_llm_invalid_output", classification="unsupported_summary")
    tags = dict(item.tags) if isinstance(item.tags, dict) else {}
    tags[QUICK_READ_MARKER] = {
        "version": QUICK_READ_VERSION,
        "state": "title_only" if material.kind == "title_only" else "ready",
        "titleZh": output.titleZh.strip(),
        "summaryZh": output.summaryZh.strip() if output.summaryZh else None,
        "materialKind": material.kind,
        "materialSha256": material.digest,
        "inputIdentity": identity,
        "sourceTitleSha256": _text_digest(item.title),
        "sourceSummarySha256": _text_digest(item.summary),
        "promptVersion": QUICK_READ_PROMPT_VERSION,
        "schemaVersion": QUICK_READ_SCHEMA_VERSION,
        "routeIdentity": route_identity,
        "provider": metadata.provider,
        "model": metadata.model_display_name,
        "reasoningEffort": metadata.reasoning_effort,
        "generatedAt": datetime.now(UTC).isoformat(),
    }
    tags.pop(QUICK_READ_FAILURE_MARKER, None)
    item.tags = tags


def _save_failure(item: ContentItem, *, identity: str, code: str) -> None:
    tags = dict(item.tags) if isinstance(item.tags, dict) else {}
    tags[QUICK_READ_FAILURE_MARKER] = {
        "version": QUICK_READ_VERSION,
        "inputIdentity": identity,
        "errorCode": code[:80],
        "failedAt": datetime.now(UTC).isoformat(),
    }
    item.tags = tags


def _budget_snapshot() -> tuple[Any | None, dict[str, Any] | None]:
    try:
        configured = execution_budget(RardarLLMScene.NEWS_QUICKREAD.value)
    except ProviderBudgetError:
        raise
    if configured is None:
        return None, None
    return configured[0], configured[0].snapshot()


async def enhance_hotspot_news(
    db: AsyncSession,
    *,
    item_limit: int = 18,
    caller: StructuredCaller = call_rardar_structured,
    route_resolver: RouteResolver = resolve_rardar_route_identity,
    material_loader: MaterialLoader = _load_material,
    frozen_page: Any | None = None,
) -> HotspotNewsEnhanceResult:
    with news_writer():
        return await _enhance_hotspot_news(
            db,
            item_limit=item_limit,
            caller=caller,
            route_resolver=route_resolver,
            material_loader=material_loader,
            frozen_page=frozen_page,
        )


async def _enhance_hotspot_news(
    db: AsyncSession,
    *,
    item_limit: int,
    caller: StructuredCaller,
    route_resolver: RouteResolver,
    material_loader: MaterialLoader,
    frozen_page: Any | None,
) -> HotspotNewsEnhanceResult:
    """Enhance at most one balanced page; this never refreshes news sources."""
    if isinstance(item_limit, bool) or item_limit < 1 or item_limit > 40:
        raise ValueError("hotspot_news_enhance_limit_invalid")
    started_at = datetime.now(UTC)
    route_identity = await route_resolver()
    ledger, before_budget = _budget_snapshot()
    if frozen_page is None:
        page, _ = await load_hotspot_news(db, sort="balanced", page=1, page_size=item_limit)
    else:
        page = frozen_page
    repository = RardarHotspotNewsRepository(db)
    rows = await repository.list_items_by_ids(item_ids=[item.id for item in page.items])
    rows_by_id = {item.id: item for item in rows}
    public_by_id = {item.id: item for item in page.items}
    results: list[HotspotNewsEnhanceItemResult] = []
    exhausted = False
    last_provider_error: str | None = None
    consecutive_provider_errors = 0

    for content_id in [item.id for item in page.items]:
        row = rows_by_id.get(content_id)
        public = public_by_id[content_id]
        if row is None:
            continue
        if _already_readable_chinese(row, public.language):
            results.append(
                HotspotNewsEnhanceItemResult(
                    contentId=row.id,
                    sourceKey=public.sourceKey,
                    status="already_chinese",
                )
            )
            continue
        material = await material_loader(db, row, public.sourceKey)
        # Reader snapshots/events are an independent source cache. Keep them
        # even if the later model request fails or exhausts its budget.
        await db.commit()
        identity = _identity(row, material, route_identity)
        if _current_marker(row, identity=identity) is not None:
            results.append(
                HotspotNewsEnhanceItemResult(
                    contentId=row.id,
                    sourceKey=public.sourceKey,
                    status="cached",
                    materialKind=material.kind,
                )
            )
            continue
        try:
            generated = await caller(
                scene=RardarLLMScene.NEWS_QUICKREAD,
                messages=_messages(row, material),
                response_model=_QuickReadOutput,
                prompt_version=QUICK_READ_PROMPT_VERSION,
                schema_version=QUICK_READ_SCHEMA_VERSION,
                reasoning_effort=ReasoningEffort.MEDIUM,
            )
            await db.refresh(row)
            if identity != _identity(row, material, route_identity):
                raise RardarLLMError("rardar_news_source_changed", classification="source_changed")
            _save_success(
                row,
                output=generated.value,
                material=material,
                identity=identity,
                route_identity=route_identity,
                metadata=generated.metadata,
            )
            await db.commit()
            last_provider_error = None
            consecutive_provider_errors = 0
            results.append(
                HotspotNewsEnhanceItemResult(
                    contentId=row.id,
                    sourceKey=public.sourceKey,
                    status="enhanced",
                    materialKind=material.kind,
                )
            )
        except RardarLLMError as exc:
            await db.rollback()
            refreshed = (await repository.list_items_by_ids(item_ids=[content_id]))[0]
            _save_failure(refreshed, identity=identity, code=exc.code)
            await db.commit()
            exhausted = exc.code == "provider_budget_exhausted"
            results.append(
                HotspotNewsEnhanceItemResult(
                    contentId=content_id,
                    sourceKey=public.sourceKey,
                    status="budget_exhausted" if exhausted else "failed",
                    materialKind=material.kind,
                    errorCode=exc.code,
                )
            )
            if exhausted:
                break
            if exc.code == last_provider_error:
                consecutive_provider_errors += 1
            else:
                last_provider_error = exc.code
                consecutive_provider_errors = 1
            if consecutive_provider_errors >= 2:
                break

    after_budget = ledger.snapshot() if ledger is not None else None
    provider_calls = (
        int(after_budget["attempted"]) - int(before_budget["attempted"])
        if after_budget is not None and before_budget is not None
        else 0
    )
    budget_remaining = int(after_budget["remaining"]) if after_budget is not None else 0
    counts = {
        status: sum(item.status == status for item in results)
        for status in {"enhanced", "cached", "already_chinese", "failed"}
    }
    return HotspotNewsEnhanceResult(
        status="budget_exhausted" if exhausted else "degraded" if counts["failed"] else "completed",
        startedAt=started_at,
        completedAt=datetime.now(UTC),
        considered=len(results),
        enhanced=counts["enhanced"],
        cacheHits=counts["cached"],
        alreadyChinese=counts["already_chinese"],
        failed=counts["failed"] + sum(item.status == "budget_exhausted" for item in results),
        providerCalls=provider_calls,
        budgetRemaining=budget_remaining,
        items=results,
    )
