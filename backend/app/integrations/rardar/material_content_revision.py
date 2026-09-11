"""Explicit evidence-bound reading repairs, retaining original Profiles and dates."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.rardar.serving_schemas import OfficialProjectProfile
from app.services.llm.provider_budget import atomic, digest, file_lock, plain

VERSION = "rardar-material-reading-v1"
TEMPLATE = re.compile(
    r"最值得继续理解的是它把|该项目把「.*作为有仓库证据支撑的主要交付能力|它把「.*让项目能力与实际采用场景形成清晰对应"
)
STATS = re.compile(r"\d[\d,.]*[kK+]*\s*(?:stars|forks|贡献者)", re.I)


def clean(text: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[>*_`#]+", "", text).strip()


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[。！？])\s*", text, maxsplit=1)[0].strip()


def derive(profile, evidence) -> dict:
    value = profile.model_dump(mode="json")
    refs = value["claimEvidenceRefs"]

    def claim(field, text, evidence_refs, ref_field=None):
        value[field] = text
        refs[text] = list(evidence_refs)
        if ref_field:
            value[ref_field] = list(evidence_refs)

    if TEMPLATE.search(value.get("coreValueZh") or ""):
        value.update(
            coreValueZh=None, coreValueEvidenceRefs=[], rardarAssessmentZh=None, rardarAssessmentEvidenceRefs=[]
        )
    summary = value.get("identitySummaryZh") or value["officialSummaryZh"]
    summary_refs = refs.get(summary, [])
    if len(STATS.findall(summary)) >= 2:
        for key, text in evidence.evidenceIndex.items():
            if key.endswith("narrative:tagline"):
                candidate = clean(text.split(": ", 1)[-1])
                candidate = re.sub(r"^来自.+?(?:获胜者|冠军)的", "", candidate)
                if re.search(r"[\u4e00-\u9fff]", candidate) and not STATS.search(candidate):
                    summary, summary_refs = candidate, [key]
                    break
    elif len(summary) > 120:
        candidate = first_sentence(summary)
        if len(candidate) >= 10:
            # Complete existing sentence only, not character truncation.
            summary = candidate
    summary = clean(summary)
    if summary != value.get("identitySummaryZh"):
        for field in ("identitySummaryZh", "officialSummaryZh", "officialTaglineZh"):
            claim(field, summary, summary_refs, "officialTaglineEvidenceRefs" if field == "officialTaglineZh" else None)
    positioning = value.get("positioningZh") or ""
    if len(positioning) > 160 or re.search(r"生产环境|高强度日常|获胜者", positioning):
        shorter = first_sentence(positioning)
        if len(shorter) >= 15:
            claim("positioningZh", shorter, value["positioningEvidenceRefs"])
    # A long author introduction can contain a useful mechanism after an em dash.
    # Preserve that actual clause, not its unsupported uniqueness/cost claim.
    original_summary = profile.identitySummaryZh or ""
    if "唯一" in original_summary and "——" in original_summary:
        mechanism = first_sentence(original_summary.split("——", 1)[1])
        if 15 <= len(mechanism) <= 160 and not re.search(r"唯一|零成本", mechanism):
            claim(
                "positioningZh",
                mechanism,
                profile.claimEvidenceRefs.get(original_summary, []),
                "positioningEvidenceRefs",
            )
            value["positioningSourceMode"] = "rardar_derived"
    for group in ("capabilities", "keyDifferentiators", "rardarDifferentiators"):
        for capability in value[group]:
            if re.search(r"(?:一切皆插件|everything.{0,5}plugin)", capability["detail"], re.I):
                capability["title"] = "插件化架构"
    # Source explicitly distinguishes live feeds from simulation and estimates.
    # Guard all three qualifiers; never infer fidelity from a project name.
    fidelity_refs = [
        key
        for key, text in evidence.evidenceIndex.items()
        if re.search(r"feeds are live or regularly refreshed", text, re.I)
        and re.search(r"traffic is simulated", text, re.I)
        and re.search(r"camera poses.*launch trajectories are coarse estimates", text, re.I)
    ]
    if fidelity_refs:
        boundary = "多数信号实时或定期更新；交通为模拟，摄像头位姿与发射轨迹为粗略估算。"
        replacements = (
            ("以真实数据呈现实时开源空间情报", "结合真实数据、模拟与估算呈现开源空间情报"),
            ("多类实时空间数据", "多类空间数据（包含模拟和估算）"),
            ("等实时数据", "等数据图层（包含模拟和估算）"),
        )
        for field in (
            "identitySummaryZh",
            "officialSummaryZh",
            "officialTaglineZh",
            "positioningZh",
            "officialPositioningZh",
        ):
            old = value.get(field)
            if not old:
                continue
            revised = old
            for before, after in replacements:
                revised = revised.replace(before, after)
            if field in ("positioningZh", "officialPositioningZh") and boundary not in revised:
                revised += " " + boundary
            ref_field = {
                "officialTaglineZh": "officialTaglineEvidenceRefs",
                "positioningZh": "positioningEvidenceRefs",
                "officialPositioningZh": "officialPositioningEvidenceRefs",
            }.get(field)
            claim(field, revised, list(dict.fromkeys([*refs.get(old, []), *fidelity_refs])), ref_field)
        for group in ("capabilities", "keyDifferentiators", "rardarDifferentiators"):
            for capability in value[group]:
                old = capability["detail"]
                if re.search(r"交通|摄像头", old):
                    revised = old.replace("等实时数据", "等数据图层") + " " + boundary
                    capability["detail"] = revised
                    capability["shortDetail"] = None
                    capability["evidenceRefs"] = list(dict.fromkeys([*capability["evidenceRefs"], *fidelity_refs]))
                    refs[revised] = capability["evidenceRefs"]
        value["capabilityBulletsZh"] = [x["detail"] for x in value["capabilities"]]
    # These are compatibility projections of the same positioning, not separate claims.
    if value.get("positioningZh") != profile.positioningZh:
        value["officialPositioningZh"] = value["positioningZh"]
        value["officialPositioningEvidenceRefs"] = value["positioningEvidenceRefs"]
    original = profile.model_dump(mode="json")
    return {key: item for key, item in value.items() if item != original.get(key)}


def _path(target, profile):
    return target / "profile-cache" / "display-content-revisions" / f"{digest(profile.model_dump(mode='json'))}.json"


def install(target: Path, profile, evidence) -> dict:
    from app.services.rardar_trending import project_material

    project_material(profile, evidence)
    fields = derive(profile, evidence)
    if not fields:
        return {"changed": False, "state": "unchanged"}
    payload = {**profile.model_dump(mode="json"), **fields}
    project_material(OfficialProjectProfile.model_validate_json(json.dumps(payload), strict=True), evidence)
    path = _path(target, profile)
    plain(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock")):
        if path.exists():
            apply_saved(target, profile, evidence, project_material(profile, evidence))
            return {"changed": False, "state": "reused"}
        record = {
            "version": VERSION,
            "sourceProfileDigest": digest(profile.model_dump(mode="json")),
            "sourceEvidenceDigest": evidence.digest,
            "sourceGeneratedAt": profile.generatedAt.isoformat(),
            "derivedAt": datetime.now(UTC).isoformat(),
            "fields": fields,
        }
        record["digest"] = digest(record)
        atomic(path, record)
    return {"changed": True, "state": "installed", "revision": record["digest"]}


def apply_saved(target: Path, profile, evidence, material: dict) -> dict:
    from app.services.rardar_trending import project_material

    path = _path(target, profile)
    plain(path, missing=True)
    if not path.exists():
        return material
    if path.stat().st_size > 200_000:
        raise ValueError("material_content_revision_oversized")
    record = json.loads(path.read_bytes())
    if not isinstance(record, dict) or not isinstance(record.get("derivedAt"), str):
        raise ValueError("material_content_revision_invalid")
    if (
        record.get("version") != VERSION
        or record.get("sourceProfileDigest") != digest(profile.model_dump(mode="json"))
        or record.get("sourceEvidenceDigest") != evidence.digest
        or record.get("fields") != derive(profile, evidence)
        or record.get("digest") != digest({k: v for k, v in record.items() if k != "digest"})
        or record.get("sourceGeneratedAt") != profile.generatedAt.isoformat()
        or datetime.fromisoformat(record["derivedAt"]).tzinfo is None
    ):
        raise ValueError("material_content_revision_invalid")
    payload = {**material["displayProfile"], **record["fields"]}
    # Trait references were added by a separately validated display revision.
    payload["claimEvidenceRefs"] = {
        **material["displayProfile"]["claimEvidenceRefs"],
        **record["fields"].get("claimEvidenceRefs", {}),
    }
    revised = OfficialProjectProfile.model_validate_json(json.dumps(payload), strict=True)
    projected = project_material(revised, evidence)
    return {
        **material,
        "displayProfile": projected["displayProfile"],
        "profile": projected["profile"],
        "material": {
            **material["material"],
            "contentRevision": {
                k: record[k]
                for k in (
                    "version",
                    "sourceProfileDigest",
                    "sourceEvidenceDigest",
                    "sourceGeneratedAt",
                    "derivedAt",
                    "digest",
                )
            },
        },
    }
