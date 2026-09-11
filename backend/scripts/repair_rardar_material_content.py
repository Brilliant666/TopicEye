"""Preview or explicitly install bounded reading revisions; no models or fetches."""

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.integrations.rardar.material_content_revision import VERSION, derive, install
from app.integrations.rardar.project_identity import canonical_repository
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ProjectEvidenceProjection
from app.services.rardar_trending import load_saved_project_profile, saved_materials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and not 1 <= len(args.repository) <= 40:
        parser.error("--apply requires 1 to 40 explicit repositories")
    if not settings.RARDAR_INTELLIGENCE_DATA_DIR:
        parser.error("data directory is not configured")
    target = Path(settings.RARDAR_INTELLIGENCE_DATA_DIR)
    chosen = {canonical_repository(x) for x in args.repository}
    results = []
    for repository, material in sorted(saved_materials(target).items()):
        if chosen and repository not in chosen:
            continue
        provenance = material["material"]
        revision = provenance.get("contentRevision") or provenance.get("traitRevision")
        if revision:
            original = load_saved_project_profile(
                target, repository, original_profile_digest=revision["sourceProfileDigest"]
            )
            if original is None:
                raise ValueError("original_profile_missing")
            profile, evidence = original
        else:
            profile = OfficialProjectProfile.model_validate_json(json.dumps(material["displayProfile"]), strict=True)
            evidence = ProjectEvidenceProjection.model_validate_json(
                json.dumps(material["displayEvidence"]), strict=True
            )
        fields = derive(profile, evidence)
        if fields:
            before = profile.model_dump(mode="json")
            results.append(
                {
                    "repository": repository,
                    "sourceGeneratedAt": before["generatedAt"],
                    "changes": {
                        k: {"before": before[k], "after": v} for k, v in fields.items() if k != "claimEvidenceRefs"
                    },
                    **(install(target, profile, evidence) if args.apply else {"state": "dry_run"}),
                }
            )
    print(json.dumps({"version": VERSION, "providerCalls": 0, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
