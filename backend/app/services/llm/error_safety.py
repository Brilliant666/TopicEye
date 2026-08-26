"""Safe, bounded diagnostics for failures at the shared LLM boundary.

Provider exceptions are not a trustworthy display surface: SDKs and gateways
may echo request bodies, Authorization headers, endpoint query strings, or the
decrypted API key.  Persist and return only a coarse operational category.
"""

from __future__ import annotations

import asyncio


def safe_llm_error(error: BaseException) -> str:
    """Return a non-secret diagnostic without copying the exception message."""
    name = type(error).__name__
    lowered = f"{name} {error}".lower()
    if isinstance(error, TimeoutError | asyncio.TimeoutError) or "timeout" in lowered:
        category = "upstream_timeout"
    elif "429" in lowered or "rate limit" in lowered or "ratelimit" in lowered:
        category = "upstream_rate_limited"
    elif any(marker in lowered for marker in ("badrequest", "400", "contentpolicy", "unprocessable")):
        category = "request_rejected"
    elif "circuit" in lowered:
        category = "circuit_open"
    else:
        category = "upstream_unavailable"
    return f"{name}: {category}"
