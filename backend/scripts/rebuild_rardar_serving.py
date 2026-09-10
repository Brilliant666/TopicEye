"""Rebuild Rardar's immutable local serving projection from the active raw generation."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import tempfile
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


def real_profile_provider(
    *, translate_top: int, concurrency: int = 4, allow_model_generation: bool = True
) -> ProfileProvider:
    def provider(projects, generation_id, cache_root):
        return asyncio.run(
            build_official_profiles(
                projects,
                generation_id,
                cache_root,
                translate_top=translate_top,
                concurrency=concurrency,
                allow_model_generation=allow_model_generation,
            )
        )

    return provider


def rebuild(
    target: Path,
    *,
    translate_top: int = 20,
    concurrency: int = 4,
    offline: bool = False,
    publication_audit: Path | None = None,
    generate_profiles: bool = False,
) -> dict[str, object]:
    _require_generation_budget(generate_profiles)
    source = _load_rebuild_source(target)
    return _build_and_install(
        target,
        source,
        profile_provider=None
        if offline
        else real_profile_provider(
            translate_top=translate_top, concurrency=concurrency, allow_model_generation=generate_profiles
        ),
        publication_audit=publication_audit,
    )


async def rebuild_async(
    target: Path,
    *,
    translate_top: int = 20,
    concurrency: int = 4,
    offline: bool = False,
    publication_audit: Path | None = None,
    generate_profiles: bool = False,
    model_project_ids: set[int] | None = None,
) -> dict[str, object]:
    """Application entry: shared async DB/model services stay on the caller loop.

    The CLI's synchronous provider owns an event loop only in its standalone
    process. Scheduling it in a thread would reuse the application's asyncpg
    pool on a foreign loop. Only file projection work belongs in the thread.
    """
    _require_generation_budget(generate_profiles)
    source = await asyncio.to_thread(_load_rebuild_source, target)
    provider = None
    if not offline:
        board = source[0]
        profiles = await build_official_profiles(
            list(board.exactRanked[:20]),
            board.generationId,
            target / "profile-cache",
            translate_top=translate_top,
            concurrency=concurrency,
            allow_model_generation=generate_profiles,
            model_project_ids=model_project_ids,
        )

        def provider(_projects, _generation_id, _cache_root):
            return profiles

    return await asyncio.to_thread(
        _build_and_install_current,
        target,
        source,
        profile_provider=provider,
        publication_audit=publication_audit,
    )


def _build_and_install_current(target: Path, source, *, profile_provider, publication_audit: Path | None):
    # Same exclusion protocol as sync_rardar_intelligence, not a second writer
    # lock. Hold only across local verification/build/install, never model IO.
    lock_path = target.parent / f".{target.name}.sync.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ServingProjectionError("rardar_sync_already_running", "Another sync owns the mirror") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
            handle.flush()
        current = _load_rebuild_source(target)
        if (current[0].generationId, *current[1:3]) != (source[0].generationId, *source[1:3]):
            raise ServingProjectionError("rardar_serving_source_changed", "Source changed during profile collection")
        return _build_and_install(
            target,
            source,
            profile_provider=profile_provider,
            publication_audit=publication_audit,
        )
    finally:
        lock_path.unlink(missing_ok=True)


def _require_generation_budget(generate_profiles: bool) -> None:
    if generate_profiles:
        from app.services.llm.provider_budget import ProviderBudgetError, execution_budget

        if execution_budget("rardar_project_profile") is None:
            raise ProviderBudgetError("provider_budget_missing")


def _load_rebuild_source(target: Path):
    board = RardarIntelligenceAdapter.from_config(str(target)).load_explosion_board()
    if not board.generationId:
        raise ServingProjectionError("rardar_serving_source_invalid", "Active raw generation is unavailable")
    manifest_sha256, explosion_sha256 = source_hashes(target, board.generationId)
    metadata = load_sync_metadata(str(target), board.generationId)
    return board, manifest_sha256, explosion_sha256, metadata


def _build_and_install(target: Path, source, *, profile_provider, publication_audit: Path | None) -> dict[str, object]:
    board, manifest_sha256, explosion_sha256, metadata = source
    built = build_serving_projection(
        board=board,
        source_manifest_sha256=manifest_sha256,
        source_explosion_sha256=explosion_sha256,
        synced_at=datetime.fromisoformat(metadata["syncedAt"]) if metadata else None,
        source_host=metadata["sourceHost"] if metadata else None,
        cache_root=target / "profile-cache",
        profile_provider=profile_provider,
    )
    try:
        installed = install_serving_projection(target, built)
    except ServingProjectionError as exc:
        if publication_audit is not None and exc.audit is not None:
            _write_json_atomic(publication_audit, exc.audit)
        raise
    if publication_audit is not None:
        _write_json_atomic(publication_audit, installed.publication_audit)
    profiles = built.profile_result
    return {
        "status": "healthy",
        "sourceGenerationId": installed.source_generation_id,
        "servingGenerationId": installed.serving_generation_id,
        "manifestSha256": installed.manifest_sha256,
        "created": installed.created,
        "changed": installed.changed,
        "profiles": built.profile_summary.model_dump(mode="json"),
        "profileFailureCodes": {
            str(identifier): item.profile_failure_code
            for identifier, item in profiles.profiles.items()
            if item.profile_failure_code
        },
        "githubRequests": profiles.github_requests,
        "readmeCacheHits": profiles.readme_cache_hits,
        "translationCalls": profiles.translation_calls,
        "translationCacheHits": profiles.translation_cache_hits,
        "publicationAudit": installed.publication_audit,
    }


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a validated local Rardar serving projection")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--translate-top", type=int, default=20, choices=range(0, 21), metavar="0..20")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 9), metavar="1..8")
    parser.add_argument("--offline", action="store_true", help="Use only audited Artifact facts; intended for fixtures")
    parser.add_argument("--publication-audit", type=Path)
    parser.add_argument(
        "--generate-profiles",
        action="store_true",
        help="Explicitly allow model enrichment; requires the existing execution budget",
    )
    arguments = parser.parse_args()
    try:
        result = rebuild(
            arguments.target,
            translate_top=arguments.translate_top,
            concurrency=arguments.concurrency,
            offline=arguments.offline,
            publication_audit=arguments.publication_audit,
            generate_profiles=arguments.generate_profiles,
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
