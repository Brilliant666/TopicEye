"""
LLM service layer — unified AI calls via litellm.

Features:
- Primary + fallback provider support with automatic failover
- Rate limit detection (429) → auto-degrade to fallback
- Recovery check → auto-switch back to primary
- Rate limiting (token bucket)
- Retry with exponential backoff
- Structured JSON output parsing
"""

from __future__ import annotations

import json
import logging
import time
import asyncio
from typing import Any, Optional
from datetime import datetime, timedelta
import threading

from litellm import completion
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from app.config import settings

logger = logging.getLogger(__name__)


# ── DB-backed model config cache ──────────────────────────────────────

class ModelConfigCache:
    """
    Caches primary/fallback model config from DB.
    Refreshes every 60 seconds so changes in the UI take effect quickly.
    """
    def __init__(self):
        self._primary = None
        self._fallback = None
        self._last_refresh = 0.0
        self._lock = asyncio.Lock()

    async def refresh(self):
        """Reload model configs from DB."""
        try:
            from app.core.database import async_session
            from app.models.llm_model import LlmModel
            from sqlalchemy import select

            async with async_session() as session:
                result = await session.execute(
                    select(LlmModel).where(LlmModel.enabled == True)
                )
                models = result.scalars().all()

                primary = None
                fallback = None
                for m in models:
                    if m.is_primary and not primary:
                        primary = m
                    if m.is_fallback and not fallback:
                        fallback = m

                self._primary = primary
                self._fallback = fallback
                self._last_refresh = time.monotonic()
                if primary:
                    logger.debug("ModelConfigCache: primary=%s", primary.model_id)
                if fallback:
                    logger.debug("ModelConfigCache: fallback=%s", fallback.model_id)
        except Exception as e:
            logger.warning("ModelConfigCache refresh failed: %s", e)

    async def get_primary(self):
        if time.monotonic() - self._last_refresh > 60:
            async with self._lock:
                if time.monotonic() - self._last_refresh > 60:
                    await self.refresh()
        return self._primary

    async def get_fallback(self):
        if time.monotonic() - self._last_refresh > 60:
            async with self._lock:
                if time.monotonic() - self._last_refresh > 60:
                    await self.refresh()
        return self._fallback


_model_cache = ModelConfigCache()

# ── Model failover state tracker ──────────────────────────────────────

class ModelFailover:
    """
    Tracks primary model health and manages auto-failover to backup.

    States:
    - HEALTHY: primary is working normally
    - DEGRADED: primary got 429, using fallback; resumes at the exact reset time
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"

    def __init__(self):
        self._state = self.HEALTHY
        self._reset_at: Optional[datetime] = None  # exact reset time from 429
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def on_rate_limit(self, reset_at: Optional[datetime] = None):
        """Called when primary model returns 429. Pass reset_at if available."""
        with self._lock:
            if self._state == self.HEALTHY:
                logger.warning("ModelFailover: PRIMARY rate-limited, switching to FALLBACK")
            self._state = self.DEGRADED
            self._reset_at = reset_at
            if reset_at:
                logger.info("ModelFailover: will probe PRIMARY again at %s", reset_at)

    def on_success(self, used_primary: bool):
        """Called after a successful LLM call."""
        with self._lock:
            if used_primary and self._state != self.HEALTHY:
                logger.info("ModelFailover: PRIMARY recovered, switching back")
                self._state = self.HEALTHY
                self._reset_at = None

    def should_skip_primary(self) -> bool:
        """Return True if we should use fallback. Check reset time before probing."""
        with self._lock:
            if self._state == self.HEALTHY:
                return False

            if self._state == self.DEGRADED:
                # If we have an exact reset time, only probe once it's passed
                if self._reset_at:
                    now = datetime.utcnow()
                    if now < self._reset_at:
                        # Still within cooldown, use fallback
                        return True
                    else:
                        # Reset time passed, allow primary this call
                        logger.info("ModelFailover: reset time passed, trying PRIMARY")
                        return False
                return True

            return False


# Global failover tracker
_failover = ModelFailover()


# ── Rate limiter (simple token bucket) ────────────────────────────────

class RateLimiter:
    """Simple token-bucket rate limiter for LLM API calls."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._tokens = max_requests
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            refill = int(elapsed / self.window * self.max_requests)
            if refill > 0:
                self._tokens = min(self.max_requests, self._tokens + refill)
                self._last_refill = now

            if self._tokens <= 0:
                sleep_time = self.window / self.max_requests
                logger.warning("Rate limiter: waiting %.1fs", sleep_time)
                await asyncio.sleep(sleep_time)
                self._tokens = 1

            self._tokens -= 1


# Global rate limiter
_rate_limiter = RateLimiter(
    max_requests=settings.LLM_REQUESTS_PER_MINUTE,
    window_seconds=60,
)


# ── LLM call wrapper ──────────────────────────────────────────────────

def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect if an exception is a rate limit (429) error."""
    msg = str(exc).lower()
    return any(k in msg for k in ["429", "rate limit", "rate_limit", "quota exceeded",
                                   "请求过于频繁", "调用额度", "额度用完", "已达"])


def _parse_reset_time(exc: Exception) -> Optional[datetime]:
    """Parse the exact reset time from a rate limit error message.

    Handles formats like:
    - "您的限额将在 2026-05-18 21:11:16 重置"
    - "...reset at 2026-05-18T21:11:16..."
    Returns UTC datetime or None if not parseable.
    """
    import re
    msg = str(exc)
    # Match Chinese format: "2026-05-18 21:11:16"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})", msg)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                         int(m.group(4)), int(m.group(5)), int(m.group(6)))
            # Chinese servers are likely CST (UTC+8)
            from datetime import timezone, timedelta
            cst = timezone(timedelta(hours=8))
            dt = dt.replace(tzinfo=cst)
            return dt.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            pass
    return None


async def _call_llm_single(
    messages: list,
    model: str,
    api_key: Optional[str],
    api_base: Optional[str],
    temperature: float,
    max_tokens: int,
    response_format: Optional[dict],
) -> str:
    """Make a single LLM call (no retry)."""
    await _rate_limiter.acquire()

    # Resolve model name: if api_base points to open.bigmodel.cn,
    # use openai/ prefix (compatible endpoint); otherwise use bare model name.
    resolved_model = model
    if api_base and "open.bigmodel.cn" in api_base:
        # Z.AI / BigModel uses OpenAI-compatible endpoint
        if "/" not in model:
            resolved_model = f"openai/{model}"

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    if response_format:
        kwargs["response_format"] = response_format

    logger.info("LLM call: model=%s, messages=%d", resolved_model, len(messages))

    response = await asyncio.to_thread(completion, **kwargs)
    content = response.choices[0].message.content
    logger.info("LLM response: %d chars", len(content) if content else 0)
    return content or ""


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)
async def _call_with_retry(
    messages: list,
    model: str,
    api_key: Optional[str],
    api_base: Optional[str],
    temperature: float,
    max_tokens: int,
    response_format: Optional[dict],
) -> str:
    """Call LLM with a short retry on failure (not rate limit)."""
    return await _call_llm_single(
        messages, model, api_key, api_base, temperature, max_tokens, response_format
    )


async def call_llm(
    messages: list,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    use_fallback: bool = True,
) -> str:
    """
    Call LLM with automatic primary→fallback failover.

    Model config resolution order:
    1. DB llm_models table (if primary/fallback configured there)
    2. .env settings (legacy fallback)
    """
    # Try DB-backed config first
    db_primary = await _model_cache.get_primary()
    db_fallback = await _model_cache.get_fallback()

    if db_primary:
        primary_model = db_primary.model_id
        primary_key = db_primary.api_key or settings.get_primary_api_key()
        primary_base = db_primary.api_base or settings.get_primary_base_url()
        temperature = temperature or db_primary.temperature
        max_tokens = max_tokens or db_primary.max_tokens
    else:
        primary_model = settings.get_primary_model()
        primary_key = settings.get_primary_api_key()
        primary_base = settings.get_primary_base_url()

    if db_fallback:
        fallback_model = db_fallback.model_id
        fallback_key = db_fallback.api_key
        fallback_base = db_fallback.api_base
    else:
        fallback_model = settings.get_fallback_model()
        if fallback_model:
            fallback_key = settings.get_fallback_api_key(fallback_model)
            fallback_base = settings.get_fallback_base_url(fallback_model)
        else:
            fallback_key = None
            fallback_base = None

    if not fallback_model:
        # No fallback configured, just call primary
        return await _call_with_retry(
            messages, primary_model, primary_key, primary_base,
            temperature, max_tokens, None,
        )

    is_degraded = _failover.should_skip_primary()
    used_primary = not is_degraded

    # ── Step 1: Try primary (if not degraded) ─────────────────────────
    if not is_degraded:
        try:
            result = await _call_with_retry(
                messages, primary_model, primary_key, primary_base,
                temperature, max_tokens, None,
            )
            _failover.on_success(used_primary=True)
            return result
        except Exception as exc:
            if _is_rate_limit_error(exc):
                reset_time = _parse_reset_time(exc)
                _failover.on_rate_limit(reset_at=reset_time)
                logger.warning("Primary LLM rate-limited, switching to fallback: %s", exc)
            else:
                logger.warning("Primary LLM failed (non-rate-limit): %s", exc)
            # Fall through to fallback

    # ── Step 2: Try fallback ──────────────────────────────────────────
    logger.info("Calling fallback model: %s", fallback_model)
    try:
        result = await _call_with_retry(
            messages, fallback_model, fallback_key, fallback_base,
            temperature, max_tokens, None,
        )
        _failover.on_success(used_primary=False)
        return result
    except Exception as exc:
        logger.error("Fallback LLM also failed: %s", exc)
        raise


async def call_llm_json(
    messages: list,
    temperature: float = 0.2,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Call LLM and parse JSON response.

    Retries once on empty/unparseable response before giving up.
    """
    raw = ""
    for attempt in range(2):
        raw = await call_llm(messages, temperature=temperature, max_tokens=max_tokens)

        # Try to extract JSON from markdown code blocks or raw text
        text = raw.strip()
        if not text:
            logger.warning("LLM returned empty response (attempt %d)", attempt + 1)
            if attempt == 0:
                continue
            return {"raw_response": raw}

        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            result = json.loads(text)
            if not isinstance(result, dict) or not result:
                logger.warning("LLM JSON is empty or not a dict (attempt %d): %s", attempt + 1, str(result)[:200])
                if attempt == 0:
                    continue
            return result
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response (attempt %d): %s", attempt + 1, text[:200])
            if attempt == 0:
                continue

    return {"raw_response": raw}
