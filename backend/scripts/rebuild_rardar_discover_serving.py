"""Rebuild Discover Serving from the already verified local raw mirror."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.discover import DiscoverArtifactAdapter
from app.integrations.rardar.discover_serving import build_discover_serving, install_discover_serving
from scripts.rebuild_rardar_serving import real_profile_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild immutable Rardar Discover Serving")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--translate-top", type=int, default=30, choices=range(0, 31), metavar="0..30")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 9), metavar="1..8")
    arguments = parser.parse_args()
    try:
        source = DiscoverArtifactAdapter.from_config(str(arguments.target)).load()
        built = build_discover_serving(
            source,
            cache_root=arguments.target / "discover-profile-cache",
            profile_provider=real_profile_provider(
                translate_top=arguments.translate_top,
                concurrency=arguments.concurrency,
            ),
        )
        installed = install_discover_serving(arguments.target, built)
    except Exception as exc:
        code = getattr(exc, "code", "rardar_discover_serving_rebuild_failed")
        print(json.dumps({"status": "failed", "code": code}, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "healthy",
                "discoverGenerationId": installed.discover_generation_id,
                "servingGenerationId": installed.serving_generation_id,
                "created": installed.created,
                "changed": installed.changed,
                "profileSummary": built.profile_summary.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
