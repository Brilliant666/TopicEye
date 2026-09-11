import json
from types import SimpleNamespace

import pytest

from app.integrations.rardar import material_content_revision as revision
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
from app.integrations.rardar.serving_schemas import OfficialProjectProfile
from app.services import rardar_trending as service
from tests_rardar_llm.test_managed_materials import seed


def test_markdown_cleanup_preserves_technical_meaning():
    assert (
        revision.clean("> **支持 C# 与 snake_case**，版本 > 3；[原文](https://example.test)。")
        == "支持 C# 与 snake_case，版本 > 3；原文。"
    )


def test_banner_fallback_keeps_actual_description_reference():
    from app.integrations.rardar.serving_profiles import _source_claims

    banner = SimpleNamespace(purpose="overview", excerpts=["140K+ stars | 21K+ forks"], listItems=[])
    summary, reference, *_ = _source_claims([banner], "A configuration collection for coding agents.")
    assert summary == "A configuration collection for coding agents."
    assert reference == "description"


@pytest.mark.asyncio
async def test_template_repair_is_explicit_immutable_reusable_and_keeps_positioning(tmp_path):
    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    template = "最值得继续理解的是它把「查询」与「服务」放在同一套项目交付中，两项能力都有官方资料可追溯。"
    original = record.profile.model_copy(
        update={
            "coreValueZh": template,
            "coreValueEvidenceRefs": ["description"],
            "rardarAssessmentZh": template,
            "rardarAssessmentEvidenceRefs": ["description"],
            "claimEvidenceRefs": {**record.profile.claimEvidenceRefs, template: ["description"]},
        }
    )
    before = path.read_bytes()
    material = service.project_material(original, record.evidence)
    assert revision.apply_saved(tmp_path, original, record.evidence, material) == material
    assert revision.install(tmp_path, original, record.evidence)["changed"]
    repaired = revision.apply_saved(tmp_path, original, record.evidence, material)
    profile = repaired["displayProfile"]
    assert profile["coreValueZh"] is None and profile["positioningZh"] == original.positioningZh
    assert profile["capabilities"] == original.model_dump(mode="json")["capabilities"]
    assert profile["generatedAt"] == original.model_dump(mode="json")["generatedAt"]
    assert repaired["displayEvidence"] == material["displayEvidence"]
    assert revision.install(tmp_path, original, record.evidence)["state"] == "reused"
    assert path.read_bytes() == before
    saved = revision._path(tmp_path, original)
    tampered = json.loads(saved.read_bytes())
    missing_date = {k: v for k, v in tampered.items() if k != "derivedAt"}
    missing_date["digest"] = revision.digest({k: v for k, v in missing_date.items() if k != "digest"})
    saved.write_text(json.dumps(missing_date), encoding="utf-8")
    with pytest.raises(ValueError, match="revision_invalid"):
        revision.apply_saved(tmp_path, original, record.evidence, material)
    tampered["fields"]["positioningZh"] = "未取得资料的功能"
    tampered["digest"] = revision.digest({k: v for k, v in tampered.items() if k != "digest"})
    saved.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="revision_invalid"):
        revision.apply_saved(tmp_path, original, record.evidence, material)


@pytest.mark.asyncio
async def test_non_template_core_and_positioning_aliases_are_preserved(tmp_path):
    record = ProfileStoreEnvelopeV2.model_validate_json((await seed(tmp_path)).read_bytes(), strict=True)
    text = "以声明式配置管理服务并提供可检索的运行日志。"
    original = record.profile.model_copy(
        update={
            "coreValueZh": text,
            "coreValueEvidenceRefs": ["description"],
            "claimEvidenceRefs": {**record.profile.claimEvidenceRefs, text: ["description"]},
        }
    )
    assert "coreValueZh" not in revision.derive(original, record.evidence)
    long_position = "支持声明式服务配置与可检索的运行日志。" + "生产环境中的运行说明。" * 20
    original = original.model_copy(
        update={
            "positioningZh": long_position,
            "officialPositioningZh": long_position,
            "claimEvidenceRefs": {**original.claimEvidenceRefs, long_position: original.positioningEvidenceRefs},
        }
    )
    fields = revision.derive(original, record.evidence)
    assert fields["positioningZh"] == fields["officialPositioningZh"] == "支持声明式服务配置与可检索的运行日志。"


@pytest.mark.asyncio
async def test_fidelity_qualification_is_idempotent_for_future_collector_profiles(tmp_path):
    record = ProfileStoreEnvelopeV2.model_validate_json((await seed(tmp_path)).read_bytes(), strict=True)
    detail = "提供交通和摄像头等实时数据。"
    capability = record.profile.capabilities[0].model_copy(update={"detail": detail, "evidenceRefs": ["description"]})
    profile = record.profile.model_copy(
        update={
            "capabilities": [capability],
            "capabilityBulletsZh": [detail],
            "claimEvidenceRefs": {**record.profile.claimEvidenceRefs, detail: ["description"]},
        }
    )
    evidence = record.evidence.model_copy(
        update={
            "evidenceIndex": {
                **record.evidence.evidenceIndex,
                "description": "Most feeds are live or regularly refreshed. Traffic is simulated. Camera poses and launch trajectories are coarse estimates.",
            }
        }
    )
    fields = revision.derive(profile, evidence)
    repaired = OfficialProjectProfile.model_validate_json(
        json.dumps({**profile.model_dump(mode="json"), **fields}), strict=True
    )
    assert repaired.capabilities[0].detail.count("交通为模拟") == 1
    assert revision.derive(repaired, evidence) == {}


@pytest.mark.asyncio
async def test_optional_revision_path_rejection_is_local_not_a_page_failure(tmp_path, monkeypatch):
    record = ProfileStoreEnvelopeV2.model_validate_json((await seed(tmp_path)).read_bytes(), strict=True)

    def reject(*args, **kwargs):
        raise revision.ProviderBudgetError("unsafe_path")

    monkeypatch.setattr(revision, "plain", reject)
    with pytest.raises(ValueError, match="material_content_revision_path_invalid"):
        revision.apply_saved(tmp_path, record.profile, record.evidence, {})
