import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.integrations.rardar import serving_profiles as profiles
from app.integrations.rardar.adapter import RardarIntelligenceAdapter


def context(generation, sha, *, description=None):
    fixture = Path(__file__).parents[1] / "tests/fixtures/rardar_intelligence/revision-a"
    project = RardarIntelligenceAdapter.from_config(str(fixture)).load_explosion_board().exactRanked[0]
    if description is not None:
        project = project.model_copy(update={"description": description})
    evidence = profiles._build_evidence_context(
        project,
        generation,
        [],
        {"path": "README.md", "sha": sha, "markdown": "# Docs\n\nBuild documentation from Markdown.\n"},
    )
    return project, evidence


def content_key(evidence):
    return profiles._digest(evidence.model_dump(mode="json", exclude={"generationId", "digest"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("sha", [None, "a" * 40])
@pytest.mark.parametrize("stage", ["official", "assessment", "positioning"])
async def test_stage_content_keys_ignore_only_generation(tmp_path, monkeypatch, sha, stage):
    captured = []
    original = profiles._model_route_cache_identity

    class KeyCaptured(Exception):
        pass

    def capture(payload, route):
        captured.append(original(payload, route))
        raise KeyCaptured

    async def deny(_payload):
        raise AssertionError("No model request in key construction test")

    monkeypatch.setattr(profiles, "_model_route_cache_identity", capture)

    async def key(generation, *, description=None, scoped=True, route="route-a"):
        project, ctx = context(generation, sha, description=description)
        original_digest = ctx.evidence.digest
        kwargs = {
            "project": project,
            "evidence": ctx.evidence,
            "cache_root": tmp_path,
            "translator": deny,
            "model_route_identity": route,
        }
        if scoped:
            kwargs["cache_evidence_identity"] = content_key(ctx.evidence)
        with pytest.raises(KeyCaptured):
            if stage == "official":
                await profiles._official_translation(**kwargs, narrative=ctx.official_narrative)
            elif stage == "assessment":
                await profiles._translation(**kwargs, stage="translation")
            else:
                await profiles._official_positioning_translation(**kwargs, source_positioning="Build documentation.")
        assert ctx.evidence.digest == original_digest
        assert ctx.evidence.generationId == generation
        return captured[-1]

    first = await key("generation-a")
    assert await key("generation-b") == first
    assert await key("generation-b", description="A changed source description.") != first
    assert await key("generation-b", route="route-b") != first
    legacy_a = await key("generation-a", scoped=False)
    legacy_b = await key("generation-b", scoped=False)
    assert (legacy_a != legacy_b) == (stage == "official" or sha is None)


@pytest.mark.asyncio
@pytest.mark.parametrize("sha", [None, "a" * 40])
async def test_positioning_content_cache_reuses_valid_result_across_generation(tmp_path, sha):
    calls = 0

    async def translate(_payload):
        nonlocal calls
        calls += 1
        return profiles.OfficialPositioningTranslation(
            translatedPositioning="使用 Markdown 编写文档，并将资料构建成可供团队阅读的文档站。"
        )

    async def run(generation, description=None):
        project, ctx = context(generation, sha, description=description)
        return await profiles._official_positioning_translation(
            project=project,
            evidence=ctx.evidence,
            source_positioning="Build documentation from Markdown.",
            cache_root=tmp_path,
            translator=translate,
            model_route_identity="route-a",
            cache_evidence_identity=content_key(ctx.evidence),
        )

    first = await run("generation-a")
    assert first.value is not None and first.calls == 1
    cached = await run("generation-b")
    assert cached.cache_hit and cached.calls == 0 and cached.value == first.value
    assert calls == 1
    changed = await run("generation-c", "A changed source description.")
    assert not changed.cache_hit and calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["official", "assessment", "positioning"])
@pytest.mark.parametrize("invalid", [False, True])
@pytest.mark.parametrize("sha", [None, "a" * 40])
async def test_same_evidence_legacy_stage_is_validated_before_reuse(tmp_path, stage, invalid, sha):
    project, ctx = context("same-generation", sha)
    ref = next(key for key in ctx.evidence.evidenceIndex if key.startswith("readme:"))
    text = "使用 Markdown 编写文档，并将资料构建成可供团队阅读的文档站。"
    narrative = replace(
        ctx.official_narrative,
        tagline="Documentation tool",
        positioning="Build documentation from Markdown.",
        highlights=(profiles.ExtractedOfficialHighlight(1, "Docs", "Build documentation.", ref),),
    )
    if stage == "official":
        value = profiles.OfficialNarrativeTranslation(
            translatedTagline="面向团队的文档构建工具。",
            translatedPositioning=text,
            translatedHighlights=[
                profiles.TranslatedOfficialHighlight(sourceOrder=1, titleZh="文档构建", detailZh=text)
            ],
        )
    elif stage == "positioning":
        value = profiles.OfficialPositioningTranslation(translatedPositioning=text)
    else:
        value = profiles.ProfileTranslation(
            summary=profiles.EvidenceClaim(text="面向团队的文档构建工具。", evidenceRefs=[ref]),
            positioning=profiles.DerivedPositioning(
                positioningZh=text,
                includedEvidenceRefs=[ref],
                includedRoles=["core_mechanism"],
            ),
            capabilities=[profiles.ServingCapability(title="文档构建", detail=text, evidenceRefs=[ref])],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
        )
    calls = 0

    async def simulated(_):
        nonlocal calls
        calls += 1
        return value

    async def run(scoped):
        kwargs = {
            "project": project,
            "evidence": ctx.evidence,
            "cache_root": tmp_path,
            "translator": simulated,
            "model_route_identity": "same-route",
        }
        if scoped:
            kwargs["cache_evidence_identity"] = content_key(ctx.evidence)
        if stage == "official":
            return await profiles._official_translation(**kwargs, narrative=narrative)
        if stage == "positioning":
            return await profiles._official_positioning_translation(**kwargs, source_positioning=narrative.positioning)
        return await profiles._translation(**kwargs, stage="translation")

    first = await run(False)
    assert first.value == value and calls == 1
    legacy = next(tmp_path.glob("*/*/*.json"))
    if invalid:
        body = json.loads(legacy.read_bytes())
        if stage == "assessment":
            body["summary"]["evidenceRefs"] = ["not-present-in-current-evidence"]
        elif stage == "official":
            body["translatedHighlights"][0]["sourceOrder"] = 2
        else:
            body["translatedPositioning"] = "安装命令 npm install"
        legacy.write_text(json.dumps(body), encoding="utf-8")
    original_bytes, original_time = legacy.read_bytes(), legacy.stat().st_mtime_ns
    resumed = await run(True)
    assert resumed.value == value
    # Legacy SHA-only assessments cannot establish whether Description changed.
    reused = not invalid and not (stage == "assessment" and sha is not None)
    assert resumed.cache_hit is reused
    assert calls == (1 if reused else 2)
    assert legacy.read_bytes() == original_bytes and legacy.stat().st_mtime_ns == original_time
    cached = await run(True)
    assert cached.cache_hit and cached.calls == 0
    assert calls == (1 if reused else 2)
