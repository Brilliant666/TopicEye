"""Idempotent database bootstrap for the isolated Rardar POC runtime."""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import async_session
from app.core.product_profile import get_product_profile
from app.models.llm_model import LlmModel


async def ensure_rardar_poc_runtime() -> None:
    profile = get_product_profile()
    if not profile.enabled:
        return
    async with async_session() as db:
        existing = await db.scalar(
            select(LlmModel).where(
                LlmModel.provider == profile.ai_provider,
                LlmModel.routing_group == profile.ai_routing_group,
            )
        )
        if existing is None:
            db.add(
                LlmModel(
                    name="Rardar POC Mock Sub2API",
                    provider=profile.ai_provider,
                    model_id=profile.ai_model,
                    api_key=None,
                    api_base="mock://sub2api/v1/responses",
                    enabled=True,
                    routing_group=profile.ai_routing_group,
                    model_family="gpt-5.6",
                    channel_name="poc-mock",
                    routing_priority=1,
                    cooldown_seconds=1,
                    temperature=0.0,
                    max_tokens=2400,
                    requests_per_minute=600,
                    description="Network-free deterministic provider for TOPICEYE-RARDAR-POC-01 only",
                    extra_params={
                        "litellm_model": profile.ai_model,
                        "pool": {"max_concurrency": 1},
                    },
                )
            )
            await db.commit()

    from app.services.llm.circuit_breaker import get_llm_circuit_breaker
    from app.services.llm.provider import invalidate_model_cache

    await invalidate_model_cache()
    breaker = get_llm_circuit_breaker(profile.ai_routing_group)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 0.25
