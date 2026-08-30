"""Audit the active Rardar Serving Top 20 without GitHub, model, or raw reads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.integrations.rardar.serving import ServingProjectionLoader
from app.integrations.rardar.serving_completeness import audit_candidate_publication


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Rardar exact Top 20 publication completeness")
    parser.add_argument("--target", type=Path, required=True)
    arguments = parser.parse_args()
    today, _etag = ServingProjectionLoader(arguments.target).load_today_with_etag()
    report = audit_candidate_publication(
        today,
        None,
        candidate_serving_id=today.servingGenerationId,
    )
    report.update(
        {
            "activationPerformed": True,
            "previousServingId": None,
            "finalServingId": today.servingGenerationId,
        }
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["activationAllowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
