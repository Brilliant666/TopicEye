import json
from types import SimpleNamespace

import pytest

from app.integrations.rardar import material_trait_revision as revision
from app.integrations.rardar.profile_cache_v2 import ProfileStoreEnvelopeV2
from app.services import rardar_trending as service
from tests_rardar_llm.test_managed_materials import seed


@pytest.mark.parametrize("record", [[], None, 1, {}, {"derivedAt": None}])
def test_malformed_optional_revision_is_a_classified_validation_error(record):
    with pytest.raises(ValueError, match="shape_invalid"):
        revision._validate(record, None, None)


@pytest.mark.asyncio
async def test_revision_is_explicit_immutable_and_shared_without_new_generation(tmp_path, monkeypatch):
    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    original = record.profile.model_copy(
        update={
            "productFormsZh": ["服务"],
            "claimEvidenceRefs": {**record.profile.claimEvidenceRefs, "服务": ["description"]},
        }
    )
    material = service.project_material(original, record.evidence)
    assert revision.apply_saved(tmp_path, original, record.evidence, material) == material
    assert not (tmp_path / "profile-cache/display-trait-revisions").exists()
    before = path.read_bytes()
    result = revision.install(tmp_path, original, record.evidence)
    assert result["changed"]
    derived = revision.apply_saved(tmp_path, original, record.evidence, material)
    assert derived["displayProfile"]["generatedAt"] == original.model_dump(mode="json")["generatedAt"]
    assert derived["displayEvidence"] == material["displayEvidence"]
    assert derived["material"]["traitRevision"]["derivedAt"]
    assert derived["displayProfile"]["productFormsZh"] != ["服务"]
    saved_path = revision._path(tmp_path, original)
    saved = saved_path.read_bytes()
    assert revision.install(tmp_path, original, record.evidence)["state"] == "reused"
    assert saved_path.read_bytes() == saved and path.read_bytes() == before
    monkeypatch.setattr(
        service,
        "_retained_serving_details",
        lambda _: [
            SimpleNamespace(
                profile=original,
                evidence=record.evidence,
                project=None,
            )
        ],
    )
    # Select the explicit original through the regular validated shared read.
    newer = original.generatedAt
    monkeypatch.setattr(
        service,
        "ProfileStoreEnvelopeV2",
        SimpleNamespace(
            model_validate_json=lambda *a, **k: (_ for _ in ()).throw(ValueError("skip_test_cache")),
        ),
    )
    loaded, evidence = service.load_saved_project_profile(tmp_path, original.repository)
    assert loaded.productFormsZh == derived["productForms"]
    assert loaded.generatedAt == newer and evidence == record.evidence


@pytest.mark.asyncio
async def test_forged_revision_or_new_source_never_inherits_old_correction(tmp_path):
    path = await seed(tmp_path)
    record = ProfileStoreEnvelopeV2.model_validate_json(path.read_bytes(), strict=True)
    original = record.profile.model_copy(
        update={
            "productFormsZh": ["服务"],
            "claimEvidenceRefs": {**record.profile.claimEvidenceRefs, "服务": ["description"]},
        }
    )
    material = service.project_material(original, record.evidence)
    revision.install(tmp_path, original, record.evidence)
    saved_path = revision._path(tmp_path, original)
    bad = json.loads(saved_path.read_bytes())
    bad["fields"]["productFormsZh"] = ["伪造能力"]
    bad["digest"] = revision.digest({k: v for k, v in bad.items() if k != "digest"})
    saved_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence_invalid"):
        revision.apply_saved(tmp_path, original, record.evidence, material)
    changed = original.model_copy(update={"productFormsZh": []})
    assert revision._path(tmp_path, changed) != saved_path
    assert revision.apply_saved(tmp_path, changed, record.evidence, material) == material
