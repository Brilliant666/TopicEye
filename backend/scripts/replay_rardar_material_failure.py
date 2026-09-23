"""Replay a private public-repository material sample without network or model calls.

The CLI accepts fixed repository/sample identifiers, never an arbitrary file
path. It prints safe classifications only; the raw candidate stays private.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _network_forbidden():
    def deny(*_args, **_kwargs):
        raise RuntimeError("material_replay_network_forbidden")

    old_connect = socket.socket.connect
    old_connect_ex = socket.socket.connect_ex
    old_create = socket.create_connection
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    try:
        yield
    finally:
        socket.socket.connect = old_connect
        socket.socket.connect_ex = old_connect_ex
        socket.create_connection = old_create


def replay(cache_root: Path, repository_id: int, sample_id: str) -> dict:
    """Use the same pure candidate validator as online generation."""
    from pydantic import ValidationError

    from app.services.llm.strict_json import StrictJSONError, loads_strict_json
    from app.services.rardar_material_failure_samples import _safe_error, load_sample

    sample = load_sample(cache_root, repository_id, sample_id)
    if sample["modelClass"] not in {
        "CoreProfileTranslation", "OfficialNarrativeTranslation", "OfficialPositioningTranslation"
    }:
        raise ValueError("material_replay_model_unsupported")
    if sample["state"] not in {"pending", "failed", "isolated"}:
        raise ValueError("material_replay_state_invalid")
    if sample.get("stage") not in {"translation", "positioning"}:
        raise ValueError("material_replay_stage_invalid")
    if (
        sample["inputPayload"].get("repository") != sample["repository"]
        or sample["evidence"].get("repository") != sample["repository"]
        or sample["evidence"].get("githubRepositoryId") != repository_id
    ):
        raise ValueError("material_replay_source_identity_mismatch")
    with _network_forbidden():
        from app.integrations.rardar import serving_profiles as profiles

        try:
            parsed = loads_strict_json(sample["raw"])
            # Import after network lockdown. These are the exact online
            # validators, not a looser replay-only approximation.
            model_class = sample["modelClass"]
            if model_class == "CoreProfileTranslation":
                wire = profiles.CoreProfileTranslation.model_validate(parsed, strict=True)
                value, isolated = profiles.validate_core_candidate(wire.model_dump(mode="python"), sample["inputPayload"])
                positioning_present = value.positioning is not None
                references = list(value.positioning.includedEvidenceRefs) if value.positioning else []
            elif model_class == "OfficialNarrativeTranslation":
                value = profiles.OfficialNarrativeTranslation.model_validate(parsed, strict=True)
                payload = sample["inputPayload"]
                highlights = payload.get("sourceHighlights")
                if not isinstance(highlights, list) or not all(isinstance(item, dict) for item in highlights):
                    raise ValueError("material_replay_narrative_input_invalid")
                narrative = profiles.ExtractedOfficialNarrative(
                    tagline=payload.get("sourceTagline"),
                    tagline_ref=None,
                    positioning=payload.get("sourcePositioning"),
                    positioning_ref=None,
                    highlights=tuple(
                        profiles.ExtractedOfficialHighlight(
                            source_order=item["sourceOrder"],
                            title=item["sourceTitle"],
                            detail=item["sourceDetail"],
                            evidence_ref="<bound-in-sample>",
                        )
                        for item in highlights
                    ),
                    issues=(),
                )
                profiles._validate_official_translation(value, narrative)
                isolated = ()
                positioning_present = bool(value.translatedPositioning)
                references = []
            else:
                value = profiles.OfficialPositioningTranslation.model_validate(parsed, strict=True)
                profiles._validate_official_positioning_translation(value)
                isolated = ()
                positioning_present = bool(value.translatedPositioning)
                references = []
            return {
                "sampleId": sample_id,
                "result": "isolated" if isolated else "valid",
                "isolatedFields": list(isolated),
                "positioningPresent": positioning_present,
                "positioningEvidenceRefs": references,
                "candidateSha256": sample["rawSha256"],
                "inputDigest": sample["inputDigest"],
                "evidenceDigest": sample["evidenceDigest"],
            }
        except (StrictJSONError, ValidationError, profiles.ProfileTranslationError) as error:
            return {
                "sampleId": sample_id,
                "result": "failed",
                "failure": _safe_error(error),
                "candidateSha256": sample["rawSha256"],
                "inputDigest": sample["inputDigest"],
                "evidenceDigest": sample["evidenceDigest"],
            }


def _self_test() -> dict:
    """Synthetic cross-process check for final Linux image, with no production mount."""
    from app.services.rardar_material_failure_samples import (
        FailureSampleContext,
        capture_raw,
        failure_sample_scope,
        finish_sample,
    )

    with tempfile.TemporaryDirectory(prefix="rardar-failure-replay-") as temporary:
        data_root = Path(temporary)
        cache_root = data_root / "profile-cache"
        cache_root.mkdir(mode=0o700)
        evidence = {
            "repository": "example/replay-fixture",
            "githubRepositoryId": 42,
            "evidenceIndex": {"description": "公开仓库资料展示与证据核对。"},
        }
        context = FailureSampleContext(
            cache_root=cache_root,
            repository="example/replay-fixture",
            repository_id=42,
            stage="positioning",
            attempt=1,
            operation_id="replay-self-test",
            input_payload={"repository": "example/replay-fixture", "evidenceIndex": evidence["evidenceIndex"]},
            evidence=evidence,
            rule_version="self-test-v1",
        )
        raw = '{"summary":{},"positioning":null,"capabilities":[]}'
        with failure_sample_scope(context):
            ref = capture_raw(
                raw,
                {"cache_hit": False},
                model_name="CoreProfileTranslation",
                prompt_version="self-test-v1",
                schema_version="self-test-v1",
            )
            finish_sample(ref, error=ValueError("schema_invalid"))
        assert ref is not None
        env = dict(os.environ)
        # The child is an entirely new process. No production data/credentials
        # or writable mount are supplied to this fixture.
        env["RARDAR_INTELLIGENCE_DATA_DIR"] = str(data_root)
        command = [
            sys.executable,
            "-m",
            "scripts.replay_rardar_material_failure",
            "--repository-id",
            "42",
            "--sample-id",
            ref.sample_id,
        ]
        completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=30, check=False)
        if completed.returncode != 0:
            raise RuntimeError("material_replay_self_test_child_failed")
        try:
            result = json.loads(completed.stdout)
        except ValueError as exc:
            raise RuntimeError("material_replay_self_test_child_invalid") from exc
        if result.get("result") != "failed" or result.get("sampleId") != ref.sample_id:
            raise RuntimeError("material_replay_self_test_mismatch")
        return {"selfTest": "PASS", "crossProcess": True, "network": "forbidden", "sampleRetained": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-id", type=int)
    parser.add_argument("--sample-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if args.repository_id is not None or args.sample_id is not None:
            parser.error("--self-test does not accept a production sample")
        result = _self_test()
    else:
        if args.repository_id is None or args.sample_id is None:
            parser.error("--repository-id and --sample-id are required")
        from app.core.config import settings

        if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
            parser.error("RARDAR_INTELLIGENCE_DATA_DIR is required")
        root = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR) / "profile-cache"
        result = replay(root, args.repository_id, args.sample_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
