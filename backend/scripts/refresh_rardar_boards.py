"""Refresh the two public repository boards through the same zero-model entry."""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import settings
from app.core.product_profile import is_rardar_product
from app.services.rardar_trending import refresh_boards, refresh_metadata


def main():
    if not is_rardar_product() or not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        raise SystemExit("rardar_boards_not_configured")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata-only", action="store_true", help="Fill current saved board metadata without boards or AI"
    )
    parser.add_argument(
        "--history-once", action="store_true", help="Also import the public historical appearance index; no AI"
    )
    args = parser.parse_args()

    async def run():
        result = (
            await refresh_metadata(Path(settings.RARDAR_INTELLIGENCE_DATA_DIR))
            if args.metadata_only
            else await refresh_boards()
        )
        if args.history_once:
            from app.integrations.rardar.trending_boards import fetch_history
            from app.integrations.rardar.trending_store import import_historical_evidence

            result["history"] = import_historical_evidence(
                Path(settings.RARDAR_INTELLIGENCE_DATA_DIR), await fetch_history()
            )
        return result

    print(json.dumps(asyncio.run(run()), ensure_ascii=False))


if __name__ == "__main__":
    main()
