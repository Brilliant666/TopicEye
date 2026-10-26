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
async def test_stage_content_keys_bind_actual_stage_input_not_board_generation(tmp_path, monkeypatch, sha, stage):
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

    async def key(
        generation, *, description=None, scoped=True, route="route-a", source_positioning="Build documentation."
    ):
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
                await profiles._official_positioning_translation(**kwargs, source_positioning=source_positioning)
        assert ctx.evidence.digest == original_digest
        assert ctx.evidence.generationId == generation
        return captured[-1]

    first = await key("generation-a")
    assert await key("generation-b") == first
    description_changed = await key("generation-b", description="A changed source description.")
    # The positioning-only translator does not receive Description. Other
    # stages do, either directly or as an extracted source tagline.
    assert (description_changed != first) is (stage != "positioning")
    if stage == "positioning":
        assert await key("generation-b", source_positioning="Build and search documentation.") != first
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

    async def run(generation, description=None, source_positioning="Build documentation from Markdown."):
        project, ctx = context(generation, sha, description=description)
        return await profiles._official_positioning_translation(
            project=project,
            evidence=ctx.evidence,
            source_positioning=source_positioning,
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
    assert changed.cache_hit and calls == 1
    changed_material = await run(
        "generation-d", source_positioning="Build documentation and a search index from Markdown."
    )
    assert not changed_material.cache_hit and calls == 2


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


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["official", "assessment", "positioning"])
async def test_unused_readme_blob_change_reuses_actual_stage_but_changed_input_does_not(tmp_path, stage):
    """Blob changes outside the submitted section are not model-input changes."""
    project, ctx = context("first", "a" * 40)
    ref = next(key for key in ctx.evidence.evidenceIndex if key.startswith("readme:"))
    text = "使用 Markdown 编写文档，并将资料构建成可供团队阅读的文档站。"
    narrative = replace(
        ctx.official_narrative,
        tagline="Documentation tool",
        positioning="Build documentation from Markdown.",
        highlights=(profiles.ExtractedOfficialHighlight(1, "Docs", "Build documentation.", ref),),
    )
    values = {
        "official": profiles.OfficialNarrativeTranslation(
            translatedTagline="面向团队的文档构建工具。",
            translatedPositioning=text,
            translatedHighlights=[
                profiles.TranslatedOfficialHighlight(sourceOrder=1, titleZh="文档构建", detailZh=text)
            ],
        ),
        "positioning": profiles.OfficialPositioningTranslation(translatedPositioning=text),
        "assessment": profiles.ProfileTranslation(
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
        ),
    }
    calls = 0

    async def model(_payload):
        nonlocal calls
        calls += 1
        return values[stage]

    async def run(evidence, *, changed=False):
        kwargs = {
            "project": project,
            "evidence": evidence,
            "cache_root": tmp_path,
            "translator": model,
            "model_route_identity": "same-route",
            "cache_evidence_identity": content_key(evidence),
        }
        if stage == "official":
            return await profiles._official_translation(
                **kwargs,
                narrative=replace(narrative, positioning="Build searchable documentation.") if changed else narrative,
            )
        if stage == "positioning":
            return await profiles._official_positioning_translation(
                **kwargs,
                source_positioning="Build searchable documentation." if changed else narrative.positioning,
            )
        return await profiles._translation(**kwargs, stage="translation")

    assert (await run(ctx.evidence)).calls == 1
    another_blob = ctx.evidence.model_copy(update={"readmeBlobSha": "b" * 40, "generationId": "next"})
    assert (await run(another_blob)).cache_hit
    assert calls == 1
    changed_evidence = another_blob.model_copy(
        update={
            "evidenceIndex": {
                **another_blob.evidenceIndex,
                ref: "README.md: Build a search index from source documents.",
            }
        }
    )
    changed = await run(changed_evidence, changed=True)
    assert not changed.cache_hit and calls == 2
