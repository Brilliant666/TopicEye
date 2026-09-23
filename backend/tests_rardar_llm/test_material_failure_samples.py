"""Synthetic only: durable failed material candidates, no provider/source access."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.rardar_material_failure_samples import (
    FailureSampleContext,
    SampleStoreUnavailable,
    capture_raw,
    current_failure_sample,
    current_operation_id,
    failure_sample_scope,
    finish_sample,
    load_sample,
    operation_scope,
    preflight,
)


def _context(root: Path, attempt: int = 1) -> FailureSampleContext:
    return FailureSampleContext(
        cache_root=root,
        repository="example/material-fixture",
        repository_id=52,
        stage="positioning",
        attempt=attempt,
        operation_id=current_operation_id(),
        input_payload={"repository": "example/material-fixture", "evidenceIndex": {"description": "公开项目资料。"}},
        evidence={"repository": "example/material-fixture", "githubRepositoryId": 52, "evidenceIndex": {"description": "公开项目资料。"}},
        rule_version="rardar-assessment-v1",
    )


def _capture(root: Path, attempt: int, raw: str):
    with failure_sample_scope(_context(root, attempt)) as scoped:
        ref = capture_raw(
            raw,
            {"actual_model": "safe-model", "cache_hit": False, "api_key": "do-not-save"},
            model_name="CoreProfileTranslation",
            prompt_version="rardar-assessment-v1",
            schema_version="rardar-project-profile-v7",
        )
        assert scoped.sample_ref == ref
        return ref


def test_capture_is_durable_bounded_and_separate_per_attempt(tmp_path: Path):
    root = tmp_path / "profile-cache"
    root.mkdir()
    preflight(root)
    with operation_scope("approved-recovery-20260923"):
        assert current_operation_id() == "approved-recovery-20260923"
        first = _capture(root, 1, "not JSON")
        second = _capture(root, 2, '{"summary":{}}')
    assert current_operation_id() is None
    assert first is not None and second is not None and first.sample_id != second.sample_id
    finish_sample(first, error=ValueError("schema_invalid"))
    finish_sample(second, error=ValueError("structure_invalid"))
    finish_sample(first, error=ValueError("ignored_duplicate"))
    saved = load_sample(root, 52, first.sample_id)
    assert saved["raw"] == "not JSON"
    assert saved["attempt"] == 1
    assert saved["operationId"] == "approved-recovery-20260923"
    assert saved["result"]["error"]["code"] == "schema_invalid"
    assert "api_key" not in saved["provider"]
    assert current_failure_sample() is None
    if os.name != "nt":
        assert first.path.stat().st_mode & 0o077 == 0
        assert first.path.parent.stat().st_mode & 0o077 == 0


def test_clean_success_removed_but_isolated_candidate_retained(tmp_path: Path):
    root = tmp_path / "profile-cache"
    root.mkdir()
    clean = _capture(root, 1, '{"summary":{"text":"你好"}}')
    isolated = _capture(root, 2, '{"summary":{"text":"你好"},"capabilities":["invalid"]}')
    assert clean and isolated
    finish_sample(clean, error=None)
    finish_sample(isolated, error=None, isolation_reasons=["capabilities_schema_invalid"])
    assert not clean.path.exists()
    saved = load_sample(root, 52, isolated.sample_id)
    assert saved["state"] == "isolated"
    assert saved["result"]["isolatedFields"] == ["capabilities_schema_invalid"]


def test_sensitive_or_oversized_candidate_fails_closed(tmp_path: Path):
    root = tmp_path / "profile-cache"
    root.mkdir()
    with failure_sample_scope(_context(root)):
        with pytest.raises(SampleStoreUnavailable, match="failure_sample_sensitive_content"):
            capture_raw(
                "Authorization: Bearer secret-value",
                {},
                model_name="CoreProfileTranslation",
                prompt_version="v1",
                schema_version="v1",
            )
        with pytest.raises(SampleStoreUnavailable, match="failure_sample_raw_oversized"):
            capture_raw(
                "x" * (256 * 1024 + 1),
                {},
                model_name="CoreProfileTranslation",
                prompt_version="v1",
                schema_version="v1",
            )
    assert not list((root / "failure-samples" / "v1").rglob("*.json"))


def test_mismatched_input_evidence_rejected_before_dispatch(tmp_path: Path):
    root = tmp_path / "profile-cache"
    root.mkdir()
    context = _context(root)
    context.input_payload["evidenceIndex"]["description"] = "另一个来源的事实。"
    with pytest.raises(SampleStoreUnavailable, match="failure_sample_source_evidence_mismatch"), failure_sample_scope(context):
        pytest.fail("untrusted input must not enter the dispatch scope")


def test_cross_process_replay_cli_self_test():
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "scripts.replay_rardar_material_failure", "--self-test"],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"crossProcess":true' in result.stdout
    assert '"selfTest":"PASS"' in result.stdout


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("{not-json", "failed"),
        ('{"summary":[],"positioning":null,"capabilities":[]}', "failed"),
        (
            '{"summary":{"text":"一个用于整理公开仓库资料的工具。","evidenceRefs":["unknown"]},"positioning":null,"capabilities":[]}',
            "failed",
        ),
        (
            json.dumps(
                {
                    "summary": {"text": "一个用于整理公开仓库资料的工具。", "evidenceRefs": ["description"]},
                    "positioning": {
                        "positioningZh": "通过收集公开仓库证据并核验来源，生成可追溯的中文定位。",
                        "includedEvidenceRefs": ["description"],
                        "includedRoles": ["identity", "core_mechanism"],
                        "excludedClauses": [],
                    },
                    "capabilities": [
                        {"title": "错误能力", "detail": "不受证据支持的能力。", "shortDetail": None, "evidenceRefs": ["unknown"]}
                    ],
                },
                ensure_ascii=False,
            ),
            "isolated",
        ),
    ],
)
def test_replay_three_failure_layers_and_optional_isolation_in_new_process(tmp_path: Path, raw: str, expected: str):
    data = tmp_path / "data"
    cache_root = data / "profile-cache"
    cache_root.mkdir(parents=True)
    ref = _capture(cache_root, 1, raw)
    assert ref is not None
    finish_sample(ref, error=ValueError("schema_invalid"))
    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["RARDAR_INTELLIGENCE_DATA_DIR"] = str(data)
    env.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1/test")
    child = subprocess.run(
        [sys.executable, "-m", "scripts.replay_rardar_material_failure", "--repository-id", "52", "--sample-id", ref.sample_id],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result["result"] == expected
    assert result["candidateSha256"] == load_sample(cache_root, 52, ref.sample_id)["rawSha256"]
    if expected == "isolated":
        assert result["positioningPresent"] is True
        assert result["positioningEvidenceRefs"] == ["description"]
        assert result["isolatedFields"]


@pytest.mark.parametrize(
    ("model_name", "payload", "raw"),
    [
        (
            "OfficialPositioningTranslation",
            {"repository": "example/material-fixture", "sourcePositioning": "A public repository research tool."},
            '{"translatedPositioning":42}',
        ),
        (
            "OfficialNarrativeTranslation",
            {"repository": "example/material-fixture", "sourceTagline": "Public tool", "sourcePositioning": "Public positioning", "sourceHighlights": []},
            '{"translatedTagline":42,"translatedPositioning":"定位","translatedHighlights":[]}',
        ),
    ],
)
def test_official_translation_models_are_replayable_in_new_process(
    tmp_path: Path, model_name: str, payload: dict, raw: str
):
    data = tmp_path / "data"
    cache_root = data / "profile-cache"
    cache_root.mkdir(parents=True)
    context = _context(cache_root)
    context.input_payload = payload
    with failure_sample_scope(context):
        ref = capture_raw(
            raw,
            {"request_model": "openai/gpt-5.6-sol", "cache_hit": False},
            model_name=model_name,
            prompt_version="official-v1",
            schema_version="rardar-project-profile-v7",
        )
        finish_sample(ref, error=ValueError("schema_invalid"))
    assert ref is not None
    env = dict(os.environ)
    env["RARDAR_INTELLIGENCE_DATA_DIR"] = str(data)
    env.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1/test")
    child = subprocess.run(
        [sys.executable, "-m", "scripts.replay_rardar_material_failure", "--repository-id", "52", "--sample-id", ref.sample_id],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout)["result"] == "failed"
    assert load_sample(cache_root, 52, ref.sample_id)["provider"]["request_model"] == "openai/gpt-5.6-sol"


@pytest.mark.parametrize(
    ("raw", "classification", "error_class"),
    [("{not-json", "invalid_json", "StrictJSONError"), ("[]", "schema_invalid", "ValidationError")],
)
def test_actual_structured_call_persists_parse_failure_then_replays_in_new_process(
    tmp_path: Path, monkeypatch, raw: str, classification: str, error_class: str
):
    """Only the Provider is replaced; real capture, parser, and disk IO run."""
    from app.integrations.rardar.serving_profiles import CoreProfileTranslation
    from app.services import rardar_llm_control as control

    data = tmp_path / "data"
    cache_root = data / "profile-cache"
    cache_root.mkdir(parents=True)

    async def provider(*_args, **_kwargs):
        return raw, {"actual_model": "openai/gpt-5.6-sol", "cache_hit": False}

    monkeypatch.setattr(control, "call_llm_with_metadata", provider)
    with failure_sample_scope(_context(cache_root)) as scoped:
        with pytest.raises(control.RardarLLMError) as raised:
            asyncio.run(
                control.call_rardar_structured(
                    scene=control.RardarLLMScene.PROJECT_PROFILE,
                    messages=[{"role": "user", "content": "synthetic public fixture"}],
                    response_model=CoreProfileTranslation,
                    prompt_version="rardar-assessment-v1",
                    schema_version="rardar-project-profile-v7",
                )
            )
        assert raised.value.classification == classification
        ref = scoped.sample_ref
    assert ref is not None
    saved = load_sample(cache_root, 52, ref.sample_id)
    assert saved["state"] == "failed"
    assert saved["result"]["error"]["errorClass"] == error_class
    env = dict(os.environ)
    env["RARDAR_INTELLIGENCE_DATA_DIR"] = str(data)
    env.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1/test")
    child = subprocess.run(
        [sys.executable, "-m", "scripts.replay_rardar_material_failure", "--repository-id", "52", "--sample-id", ref.sample_id],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    replayed = json.loads(child.stdout)
    assert replayed["result"] == "failed"
    assert replayed["failure"] == saved["result"]["error"]


def test_actual_translation_business_failure_replays_same_rule_in_new_process(tmp_path: Path, monkeypatch):
    from app.integrations.rardar import serving_profiles as profiles
    from app.services import rardar_llm_control as control

    data = tmp_path / "data"
    cache_root = data / "profile-cache"
    cache_root.mkdir(parents=True)
    raw = json.dumps(
        {
            "summary": {"text": "一个用于整理公开仓库资料的工具。", "evidenceRefs": ["unknown"]},
            "positioning": None,
            "capabilities": [],
        },
        ensure_ascii=False,
    )

    async def provider(*_args, **_kwargs):
        return raw, {"actual_model": "openai/gpt-5.6-sol", "cache_hit": False}

    monkeypatch.setattr(control, "call_llm_with_metadata", provider)
    context = _context(cache_root)
    with failure_sample_scope(context):
        with pytest.raises(profiles.ProfileTranslationError) as raised:
            asyncio.run(profiles._translate_with_control(context.input_payload))
        assert str(raised.value) == "rardar_profile_translation_evidence_mismatch"
        finish_sample(context.sample_ref, error=raised.value)
    assert context.sample_ref is not None
    saved = load_sample(cache_root, 52, context.sample_ref.sample_id)
    assert saved["result"]["error"]["code"] == "rardar_profile_translation_evidence_mismatch"
    env = dict(os.environ)
    env["RARDAR_INTELLIGENCE_DATA_DIR"] = str(data)
    env.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1/test")
    child = subprocess.run(
        [sys.executable, "-m", "scripts.replay_rardar_material_failure", "--repository-id", "52", "--sample-id", context.sample_ref.sample_id],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    replayed = json.loads(child.stdout)
    assert replayed["result"] == "failed"
    assert replayed["failure"] == saved["result"]["error"]


def test_full_translation_retry_retains_each_actual_candidate(tmp_path: Path, monkeypatch):
    from app.integrations.rardar import serving_profiles as profiles
    from app.integrations.rardar.serving_schemas import ProjectEvidenceProjection
    from app.services import rardar_llm_control as control

    cache_root = tmp_path / "data" / "profile-cache"
    cache_root.mkdir(parents=True)
    response = json.dumps(
        {"summary": {"text": "一个用于整理公开仓库资料的工具。", "evidenceRefs": ["unknown"]}, "positioning": None, "capabilities": []},
        ensure_ascii=False,
    )
    calls = 0

    async def provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return response, {"actual_model": "openai/gpt-5.6-sol", "cache_hit": False}

    monkeypatch.setattr(control, "call_llm_with_metadata", provider)
    evidence = ProjectEvidenceProjection(
        schemaVersion=1,
        githubRepositoryId=52,
        repository="example/material-fixture",
        generationId="fixture-generation",
        readmePath=None,
        readmeBlobSha=None,
        sourceLanguage="zh",
        selectedSections=[],
        originalExcerpts=[],
        topLevelTree=[],
        evidenceIndex={"description": "公开项目资料。"},
        pathRefs={},
        digest="a" * 64,
    )
    result = asyncio.run(
        profiles._translation(
            project=SimpleNamespace(githubRepositoryId=52, repository="example/material-fixture"),
            evidence=evidence,
            cache_root=cache_root,
            translator=profiles._translate_with_control,
            stage="positioning",
        )
    )
    assert result.value is None and result.error_code == "positioning_evidence_mismatch"
    assert calls == result.calls == 2
    sample_ids = sorted(path.stem for path in (cache_root / "failure-samples" / "v1" / "52").glob("*.json"))
    assert len(sample_ids) == 2
    for sample_id in sample_ids:
        saved = load_sample(cache_root, 52, sample_id)
        assert saved["state"] == "failed"
        assert saved["result"]["error"]["code"] == "rardar_profile_translation_evidence_mismatch"
