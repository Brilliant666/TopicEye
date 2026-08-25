"""Independent Rardar POC worker for durable Find Project jobs."""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.config import settings
from app.core.product_profile import get_product_profile
from app.rardar.bootstrap import ensure_rardar_poc_runtime
from app.rardar.find_project_service import process_one_find_project_job

logger = logging.getLogger(__name__)


async def run_worker(*, once: bool) -> None:
    if not get_product_profile().enabled:
        raise RuntimeError("RARDAR_PRODUCT_MODE must be enabled for the POC worker")
    await ensure_rardar_poc_runtime()
    while True:
        try:
            claimed = await process_one_find_project_job()
        except Exception:
            if once:
                raise
            logger.exception("Rardar POC worker iteration failed; durable jobs remain retryable")
            await asyncio.sleep(max(settings.RARDAR_FIND_WORKER_POLL_SECONDS, 0.25))
            continue
        if once:
            return
        if claimed is None:
            await asyncio.sleep(settings.RARDAR_FIND_WORKER_POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated Rardar Find Project POC worker")
    parser.add_argument("--once", action="store_true", help="Process at most one durable unit")
    args = parser.parse_args()
    asyncio.run(run_worker(once=args.once))


if __name__ == "__main__":
    main()
