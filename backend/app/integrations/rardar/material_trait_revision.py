"""Evidence-bound taxonomy corrections; original Profile and Evidence stay immutable."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.rardar.serving_profiles import _structured_traits
from app.integrations.rardar.serving_schemas import OfficialProjectProfile
from app.services.llm.provider_budget import atomic, digest, file_lock, plain

VERSION = "rardar-material-traits-v2"
FIELDS = ("productFormsZh", "supportedEnvironmentsZh", "deliveryFormsZh")


def derive(profile: OfficialProjectProfile, evidence) -> tuple[dict, dict]:
    forms, environments, delivery, _ = _structured_traits(evidence.evidenceIndex)
    groups = (forms, environments, delivery)
    fields = {key: [claim.text for claim in claims] for key, claims in zip(FIELDS, groups, strict=True)}
    refs = {claim.text: claim.evidenceRefs for group in groups for claim in group}
    return fields, refs


def _path(target: Path, profile) -> Path:
    return target / "profile-cache" / "display-trait-revisions" / f"{digest(profile.model_dump(mode='json'))}.json"


def _validate(record: dict, profile, evidence) -> OfficialProjectProfile:
    if not isinstance(record, dict) or not isinstance(record.get("derivedAt"), str):
        raise ValueError("material_trait_revision_shape_invalid")
    if (
        record.get("schemaVersion") != VERSION
        or record.get("sourceProfileDigest") != digest(profile.model_dump(mode="json"))
        or record.get("sourceEvidenceDigest") != evidence.digest
        or record.get("sourceGeneratedAt") != profile.generatedAt.isoformat()
        or record.get("source") != "deterministic_original_evidence_attribution"
        or record.get("repository") != profile.repository
        or record.get("githubRepositoryId") != profile.githubRepositoryId
        or record.get("digest") != digest({k: v for k, v in record.items() if k != "digest"})
    ):
        raise ValueError("material_trait_revision_binding_invalid")
    when = datetime.fromisoformat(record["derivedAt"])
    if when.tzinfo is None:
        raise ValueError("material_trait_revision_time_invalid")
    fields, refs = derive(profile, evidence)
    if record.get("fields") != fields or record.get("claimEvidenceRefs") != refs:
        raise ValueError("material_trait_revision_evidence_invalid")
    payload = profile.model_dump(mode="json")
    payload.update(fields)
    payload["claimEvidenceRefs"] = {**payload["claimEvidenceRefs"], **refs}
    return OfficialProjectProfile.model_validate_json(json.dumps(payload), strict=True)


def install(target: Path, profile, evidence) -> dict:
    """Explicit bounded repair only. GET never creates or modifies a revision."""
    # Reuse the product's complete original binding/reference validation first.
    from app.services.rardar_trending import project_material

    project_material(profile, evidence)
    fields, refs = derive(profile, evidence)
    if all(getattr(profile, key) == fields[key] for key in FIELDS):
        return {"changed": False, "state": "already_consistent"}
    path = _path(target, profile)
    plain(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock")):
        if path.exists():
            record = json.loads(path.read_bytes())
            _validate(record, profile, evidence)
            return {"changed": False, "state": "reused", "revision": record["digest"]}
        record = {
            "schemaVersion": VERSION,
            "repository": profile.repository,
            "githubRepositoryId": profile.githubRepositoryId,
            "sourceProfileDigest": digest(profile.model_dump(mode="json")),
            "sourceEvidenceDigest": evidence.digest,
            "sourceGeneratedAt": profile.generatedAt.isoformat(),
            "derivedAt": datetime.now(UTC).isoformat(),
            "source": "deterministic_original_evidence_attribution",
            "fields": fields,
            "claimEvidenceRefs": refs,
        }
        record["digest"] = digest(record)
        _validate(record, profile, evidence)
        atomic(path, record)
    return {"changed": True, "state": "installed", "revision": record["digest"]}


def apply_saved(target: Path, profile, evidence, material: dict) -> dict:
    path = _path(target, profile)
    plain(path, missing=True)
    if not path.exists():
        return material
    if path.stat().st_size > 100_000:
        raise ValueError("material_trait_revision_oversized")
    record = json.loads(path.read_bytes())
    revised = _validate(record, profile, evidence)
    return {
        **material,
        "displayProfile": revised.model_dump(mode="json"),
        "productForms": revised.productFormsZh,
        "runtimeEnvironments": revised.supportedEnvironmentsZh,
        "artifactTypes": revised.deliveryFormsZh,
        "material": {
            **material["material"],
            "traitRevision": {
                key: record[key]
                for key in (
                    "schemaVersion",
                    "derivedAt",
                    "source",
                    "sourceProfileDigest",
                    "sourceEvidenceDigest",
                    "digest",
                )
            },
        },
    }
