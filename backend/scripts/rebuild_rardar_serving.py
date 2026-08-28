"""Rebuild Rardar's immutable local serving projection from the active raw generation."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from app.integrations.rardar.adapter import RardarArtifactError, RardarIntelligenceAdapter
from app.integrations.rardar.serving import (
    ProfileProvider,
    ServingProjectionError,
    build_serving_projection,
    install_serving_projection,
    source_hashes,
)
from app.integrations.rardar.serving_profiles import build_official_profiles
from app.integrations.rardar.sync import load_sync_metadata


def real_profile_provider(*, translate_top: int, concurrency: int = 4) -> ProfileProvider:
    def provider(projects, generation_id, cache_root):
        return asyncio.run(
            build_official_profiles(
                projects,
                generation_id,
                cache_root,
                translate_top=translate_top,
                concurrency=concurrency,
            )
        )

    return provider


def rebuild(
    target: Path,
    *,
    translate_top: int = 10,
    concurrency: int = 4,
    offline: bool = False,
) -> dict[str, object]:
    board = RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board()
    if not board.generationId:
        raise ServingProjectionError("rardar_serving_source_invalid", "Active raw generation is unavailable")
    manifest_sha256, explosion_sha256 = source_hashes(target, board.generationId)
    metadata = load_sync_metadata(str(target), board.generationId)
    built = build_serving_projection(
        board=board,
        source_manifest_sha256=manifest_sha256,
        source_explosion_sha256=explosion_sha256,
        synced_at=datetime.fromisoformat(metadata["syncedAt"]) if metadata else None,
        source_host=metadata["sourceHost"] if metadata else None,
        cache_root=target / "profile-cache",
        profile_provider=None
        if offline
        else real_profile_provider(translate_top=translate_top, concurrency=concurrency),
    )
    installed = install_serving_projection(target, built)
    profiles = built.profile_result
    return {
        "status": "healthy",
        "sourceGenerationId": installed.source_generation_id,
        "servingGenerationId": installed.serving_generation_id,
        "manifestSha256": installed.manifest_sha256,
        "created": installed.created,
        "changed": installed.changed,
        "profiles": built.profile_summary.model_dump(mode="json"),
        "githubRequests": profiles.github_requests,
        "readmeCacheHits": profiles.readme_cache_hits,
        "translationCalls": profiles.translation_calls,
        "translationCacheHits": profiles.translation_cache_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a validated local Rardar serving projection")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--translate-top", type=int, default=10, choices=range(0, 21), metavar="0..20")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 9), metavar="1..8")
    parser.add_argument("--offline", action="store_true", help="Use only audited Artifact facts; intended for fixtures")
    arguments = parser.parse_args()
    try:
        result = rebuild(
            arguments.target,
            translate_top=arguments.translate_top,
            concurrency=arguments.concurrency,
            offline=arguments.offline,
        )
    except (RardarArtifactError, ServingProjectionError) as exc:
        print(json.dumps({"status": "failed", "code": exc.code}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception:
        print(
            json.dumps({"status": "failed", "code": "rardar_serving_rebuild_failed"}, sort_keys=True), file=sys.stderr
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
