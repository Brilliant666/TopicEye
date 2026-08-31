"""Rebuild Discover Serving from the already verified local raw mirror."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.discover import DiscoverArtifactAdapter
from app.integrations.rardar.discover_serving import build_discover_serving, install_discover_serving
from app.integrations.rardar.discover_sync import load_discover_sync_metadata
from app.integrations.rardar.serving import ProfileProvider
from scripts.rebuild_rardar_serving import real_profile_provider


def rebuild(
    target: Path,
    *,
    translate_top: int = 30,
    concurrency: int = 4,
    profile_provider: ProfileProvider | None = None,
) -> dict[str, object]:
    target = target.resolve()
    source = DiscoverArtifactAdapter.from_config(str(target)).load()
    metadata = load_discover_sync_metadata(target, source)
    built = build_discover_serving(
        source,
        cache_root=target / "discover-profile-cache",
        profile_provider=profile_provider
        or real_profile_provider(
            translate_top=translate_top,
            concurrency=concurrency,
        ),
        synced_at=metadata.synced_at if metadata else None,
        source_host=metadata.source_host if metadata else None,
    )
    installed = install_discover_serving(target, built)
    return {
        "status": "healthy",
        "discoverGenerationId": installed.discover_generation_id,
        "servingGenerationId": installed.serving_generation_id,
        "created": installed.created,
        "changed": installed.changed,
        "profileSummary": built.profile_summary.model_dump(mode="json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild immutable Rardar Discover Serving")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--translate-top", type=int, default=30, choices=range(0, 31), metavar="0..30")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 9), metavar="1..8")
    arguments = parser.parse_args()
    try:
        result = rebuild(
            arguments.target,
            translate_top=arguments.translate_top,
            concurrency=arguments.concurrency,
        )
    except Exception as exc:
        code = getattr(exc, "code", "rardar_discover_serving_rebuild_failed")
        print(json.dumps({"status": "failed", "code": code}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
