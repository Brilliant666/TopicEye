"""Refresh the small public Rardar Hotspot News source set once."""

from __future__ import annotations

import asyncio
import json

from app.core.database import async_session
from app.core.product_profile import is_rardar_product
from app.services.rardar_hotspot_news import refresh_hotspot_news


async def _run() -> int:
    if not is_rardar_product():
        raise RuntimeError("RARDAR_PRODUCT_MODE=true is required for Hotspot News refresh")
    async with async_session() as db:
        result = await refresh_hotspot_news(db)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {"completed", "degraded"} else 2


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
