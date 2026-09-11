"""List taxonomy changes; explicitly apply a bounded set of evidence-only revisions.

No Provider, source fetch, Profile regeneration or original-artifact overwrite.
Uses the configured data root. Default is dry-run; --apply requires repositories.
"""

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.integrations.rardar.material_trait_revision import FIELDS, VERSION, derive, install
from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ProjectEvidenceProjection
from app.services.rardar_trending import saved_materials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and not 1 <= len(args.repository) <= 16:
        parser.error("--apply requires 1 to 16 explicit repositories")
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        parser.error("RARDAR_INTELLIGENCE_DATA_DIR is not configured")
    chosen = {canonical_repository(value) for value in args.repository}
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    materials = saved_materials(target)
    results = []
    for repository, material in sorted(materials.items()):
        if chosen and repository not in chosen:
            continue
        current = material.get("material", {}).get("traitRevision", {})
        if current.get("schemaVersion") == VERSION:
            results.append({"repository": repository, "state": "reused", "revision": current["digest"]})
            continue
        profile = OfficialProjectProfile.model_validate_json(json.dumps(material["displayProfile"]), strict=True)
        evidence = ProjectEvidenceProjection.model_validate_json(json.dumps(material["displayEvidence"]), strict=True)
        fields, _ = derive(profile, evidence)
        changes = {
            key: {"before": getattr(profile, key), "after": fields[key]}
            for key in FIELDS
            if getattr(profile, key) != fields[key]
        }
        if changes:
            outcome = install(target, profile, evidence) if args.apply else {"state": "dry_run"}
            results.append(
                {
                    "repository": repository,
                    "sourceGeneratedAt": profile.generatedAt.isoformat(),
                    "changes": changes,
                    **outcome,
                }
            )
    missing = sorted(chosen - set(materials))
    print(
        json.dumps(
            {
                "version": VERSION,
                "apply": args.apply,
                "providerCalls": 0,
                "missingRepositories": missing,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
