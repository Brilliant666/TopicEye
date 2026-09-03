from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from app.integrations.rardar.discover import DiscoverArtifactAdapter
from app.integrations.rardar.selection_source import LoadedSelectionSource

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_discover"


def loaded_source(target: Path) -> LoadedSelectionSource:
    legacy = DiscoverArtifactAdapter.from_config(str(target.resolve())).load()
    top20 = sorted(int(item["githubRepositoryId"]) for item in legacy.today["exactRanked"] if int(item["rank"]) <= 20)
    published_digest = hashlib.sha256(
        (
            json.dumps(
                {"githubRepositoryIds": top20},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
    ).hexdigest()
    return LoadedSelectionSource(
        source_observation_set_id="observation-v1-fixture-source",
        pointer_raw=legacy.pointer_raw,
        manifest_sha256=legacy.manifest_sha256,
        inventory_digest=legacy.artifact_sha256,
        captures=legacy.captures,
        today=legacy.today,
        latest_capture_id=legacy.board.latestCaptureId,
        latest_capture_at=legacy.board.latestCaptureCapturedAt.isoformat(),
        source_window_start=legacy.board.sourceWindowStart.isoformat(),
        source_window_end=legacy.board.sourceWindowEnd.isoformat(),
        today_generation_id=legacy.board.todayExplosionGenerationId,
        today_explosion_sha256=legacy.board.todayExplosionDigest,
        today_published_set_digest=published_digest,
        source_coverage_state=legacy.board.coverage.state,
    )


def copy_and_load(tmp_path: Path) -> tuple[Path, LoadedSelectionSource]:
    import shutil

    target = tmp_path / "mirror"
    shutil.copytree(FIXTURE, target, dirs_exist_ok=True)
    return target, loaded_source(target)


def source_bundle() -> bytes:
    discover_pointer = json.loads((FIXTURE / "artifacts/trending/discover/v1/current.json").read_text(encoding="utf-8"))
    generation = FIXTURE / "artifacts/trending/discover/v1/generations" / discover_pointer["generationId"]
    discover = json.loads((generation / "discover.json").read_text(encoding="utf-8"))
    sources = generation / "sources"
    captures: list[dict[str, str]] = []
    capture_by_id: dict[str, bytes] = {}
    for reference in discover["sourceInventory"]:
        raw = (generation / reference["generationRelativePath"]).read_bytes()
        capture_by_id[reference["captureId"]] = raw
        captures.append(
            {
                "captureId": reference["captureId"],
                "content": base64.b64encode(raw).decode("ascii"),
            }
        )
    today_manifest_raw = (sources / "today-manifest.json").read_bytes()
    today_manifest = json.loads(today_manifest_raw)
    today_explosion_raw = (sources / "today-explosion.json").read_bytes()
    today_explosion = json.loads(today_explosion_raw)
    today_pointer = {
        "schemaVersion": 1,
        "generationId": today_manifest["generationId"],
        "publishedAt": today_manifest["createdAt"],
        "previousGenerationId": today_manifest["baseGenerationId"],
        "manifestSha256": hashlib.sha256(today_manifest_raw).hexdigest(),
    }
    generation_files: dict[str, str] = {}
    references = [today_explosion["sourceCaptures"]["current"]]
    if today_explosion["sourceCaptures"]["baseline"] is not None:
        references.append(today_explosion["sourceCaptures"]["baseline"])
    references.extend(today_explosion["sourceCaptures"]["partial"])
    if today_explosion["sourceCaptures"]["coverageWitness"] is not None:
        references.append(today_explosion["sourceCaptures"]["coverageWitness"])
    for reference in references:
        generation_files[reference["generationRelativePath"]] = base64.b64encode(
            capture_by_id[reference["captureId"]]
        ).decode("ascii")
    payload = {
        "schemaVersion": 1,
        "captures": captures,
        "today": {
            "current": base64.b64encode(
                json.dumps(today_pointer, sort_keys=True, separators=(",", ":")).encode()
            ).decode("ascii"),
            "manifest": base64.b64encode(today_manifest_raw).decode("ascii"),
            "explosion": base64.b64encode(today_explosion_raw).decode("ascii"),
            "generationFiles": generation_files,
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
