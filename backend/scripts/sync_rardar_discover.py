"""Sync and build one independently versioned Rardar Discover projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.discover_sync import DiscoverSyncError, sync_discover_intelligence
from scripts.rebuild_rardar_serving import real_profile_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync one audited Rardar Discover generation")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--host", default="rardar-prod")
    parser.add_argument("--remote-root", default="/var/lib/rardar/data")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--translate-top", type=int, default=30, choices=range(0, 31), metavar="0..30")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 9), metavar="1..8")
    arguments = parser.parse_args()
    try:
        result = sync_discover_intelligence(
            target=arguments.target,
            host=arguments.host,
            remote_root=arguments.remote_root,
            source_dir=arguments.source_dir,
            profile_provider=real_profile_provider(
                translate_top=arguments.translate_top,
                concurrency=arguments.concurrency,
            ),
        )
    except DiscoverSyncError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({"status": "healthy", **result.__dict__}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
