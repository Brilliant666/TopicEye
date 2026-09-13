"""Evidence-bound readable introductions, not complete Profiles or new model stages.

Only the existing collector writes these partial results. GET validates and reads
them; a later Profile failure cannot erase a successfully validated introduction.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.serving_schemas import ProjectEvidenceProjection
from app.services.llm.provider_budget import atomic, digest, file_lock, plain


def introduction_boilerplate(value: str | None) -> bool:
    """Exclude acknowledgements/navigation and empty slogans, not project claims.

    This is a selection rule, not a replacement for evidence/identity validation.
    In particular a Chinese translation credit is not a Chinese project intro.
    """
    text = re.sub(r"<[^>]+>", " ", value or "").strip(" *#_>\n\t")
    return bool(
        re.search(
            r"^(?:特别)?(?:感谢|致谢|鸣谢|多谢)|^(?:special\s+)?thanks?\b"
            r"|^(?:简体|繁体|中文|英文|本|该).{0,12}(?:版|译文|翻译).{0,35}"
            r"(?:由|感谢|译者|润色|校对|贡献)"
            r"|^(?:translated|translation|proofread|localized)\s+(?:by|thanks|credits)\b",
            text,
            re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:欢迎(?:使用|来到|体验)?.{0,30}|让(?:未来|世界|开发|生活).{0,20}更.{0,12}"
            r"|为.{0,20}而生|重新定义.{0,20}|你的下一个.{0,20})[！!。.]?",
            text,
        )
    )


def readable_chinese_introduction(value: str | None) -> bool:
    """Whether already validated material is useful as a short Chinese intro.

    Partial material can qualify; full Profile completeness is intentionally not
    required. This predicate alone never establishes that a claim has evidence.
    """
    from app.integrations.rardar.serving_profiles import _publishable_primary_text

    return bool(_publishable_primary_text(value) and not introduction_boilerplate(value))


def official_summary_replacement(summary: str | None, evidence: ProjectEvidenceProjection) -> tuple[str, list[str]] | None:
    """Repair only boilerplate using an exact existing native-Chinese excerpt.

    Caller must first validate the saved Profile/evidence envelope. No new
    claim, translated text, source timestamp, or Profile is manufactured here.
    """
    if readable_chinese_introduction(summary):
        return None
    for ref in ("readme:narrative:positioning", "readme:narrative:tagline"):
        source = evidence.evidenceIndex.get(ref, "")
        text = source.split(": ", 1)[1] if source.startswith(evidence.readmePath or "README") and ": " in source else source
        if readable_chinese_introduction(text):
            return text, [ref]
    return None


def _validate(payload: dict) -> ProjectEvidenceProjection:
    from app.integrations.rardar.serving_profiles import _digest

    evidence = ProjectEvidenceProjection.model_validate_json(json.dumps(payload["evidence"]), strict=True)
    refs = payload["evidenceRefs"]
    if (
        payload.get("schemaVersion") != 1
        or payload["repository"] != canonical_repository(evidence.repository)
        or payload["githubRepositoryId"] != evidence.githubRepositoryId
        or _digest(evidence.model_dump(mode="json", exclude={"digest"})) != evidence.digest
        or not readable_chinese_introduction(payload["summary"])
        or not refs
        or any(ref not in evidence.evidenceIndex or not evidence.evidenceIndex[ref].strip() for ref in refs)
        or payload["sourceMode"] not in {"official_zh", "validated_translation"}
        or datetime.fromisoformat(payload["savedAt"]).tzinfo is None
        or (payload["generatedAt"] is not None and datetime.fromisoformat(payload["generatedAt"]).tzinfo is None)
    ):
        raise ValueError("project_introduction_invalid")
    if payload["sourceMode"] == "official_zh" and not any(
        payload["summary"] in evidence.evidenceIndex[ref] for ref in refs
    ):
        raise ValueError("project_introduction_original_mismatch")
    return evidence


def save(
    cache_root: Path,
    evidence,
    summary: str,
    refs: list[str],
    *,
    source_mode: str,
    source_label: str,
    generated_at: str | None = None,
) -> dict:
    payload = {
        "schemaVersion": 1,
        "repository": canonical_repository(evidence.repository),
        "githubRepositoryId": evidence.githubRepositoryId,
        "summary": summary,
        "evidenceRefs": refs,
        "evidence": evidence.model_dump(mode="json"),
        "sourceMode": source_mode,
        "sourceLabel": source_label,
        "generatedAt": generated_at,
        "savedAt": datetime.now(UTC).isoformat(),
    }
    _validate(payload)
    # No board date, rank, stars or binding generation in the content identity.
    identity = digest(
        {
            "repository": payload["repository"],
            "repositoryId": evidence.githubRepositoryId,
            "summary": summary,
            "sourceMode": source_mode,
            "sources": {ref: evidence.evidenceIndex[ref] for ref in refs},
            "readmeBlobSha": evidence.readmeBlobSha,
        }
    )
    path = cache_root / "introductions" / str(evidence.githubRepositoryId) / f"{identity}.json"
    plain(path, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path.with_suffix(".lock")):
        if path.exists():
            return read(path)  # preserve the real first saved source and time
        atomic(path, {"payload": payload, "digest": digest(payload)})
    return payload


def read(path: Path) -> dict:
    plain(path)
    if path.stat().st_size > 12_000_000:
        raise ValueError("project_introduction_too_large")
    record = json.loads(path.read_bytes())
    payload = record["payload"]
    if record.get("digest") != digest(payload):
        raise ValueError("project_introduction_digest_invalid")
    _validate(payload)
    if path.parent.name != str(payload["githubRepositoryId"]):
        raise ValueError("project_introduction_path_identity_invalid")
    return payload


def saved(cache_root: Path) -> dict:
    root = cache_root / "introductions"
    plain(root, missing=True)
    found = {}
    for path in sorted(root.glob("*/*.json")) if root.exists() else []:
        try:
            value = read(path)
            repo = value["repository"]
            previous = found.get(repo)
            if previous is None or value["savedAt"] > previous["savedAt"]:
                found[repo] = value
        except (ValueError, KeyError, TypeError, OSError):
            continue
    return found


def material(value: dict) -> dict:
    evidence = _validate(value)
    return {
        "repository": value["repository"],
        "githubRepositoryId": value["githubRepositoryId"],
        "materialState": "partial",
        "displayProfile": None,
        "displayEvidence": None,
        "profile": {
            "summary": value["summary"],
            "positioning": None,
            "capabilities": [],
            "useCases": [],
            "limitations": None,
            "startHere": [],
            "sourceLabel": value["sourceLabel"],
            "sourceUrl": f"https://github.com/{value['repository']}",
            "generatedAt": value["generatedAt"],
            "savedAt": value["savedAt"],
            "sourceRevision": evidence.digest,
            "sourceGeneration": evidence.generationId,
            "evidenceRefs": value["evidenceRefs"],
            "summaryEvidence": [
                {
                    "ref": ref,
                    "text": evidence.evidenceIndex[ref],
                    "url": f"https://github.com/{value['repository']}"
                    + (
                        f"/blob/HEAD/{quote(evidence.pathRefs.get(ref) or evidence.readmePath, safe='/#')}"
                        if ref != "description" and (evidence.pathRefs.get(ref) or evidence.readmePath)
                        else ""
                    ),
                }
                for ref in value["evidenceRefs"]
            ],
        },
        "material": {
            "schemaVersion": 2,
            "sourceKind": "partial_introduction",
            "generatedAt": value["generatedAt"],
            "savedAt": value["savedAt"],
            "sourceGeneration": evidence.generationId,
            "sourceRevision": evidence.digest,
        },
    }
