"""Explicit local-only freeze/init/run/install steps. Never starts a scheduler."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.core.config import settings
from app.integrations.rardar.shadow_change_resume import ARTIFACT_NAME
from app.integrations.rardar.shadow_cohort import freeze
from app.integrations.rardar.shadow_review import build_shadow_review, resume_meaningful_change
from app.integrations.rardar.shadow_schemas import ShadowReviewArtifact
from app.integrations.rardar.shadow_serving import install_shadow
from app.services.llm.provider_budget import ProviderBudgetLedger
from app.services.rardar_llm_control import resolve_rardar_route_identity


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("freeze", "initialize-budget", "run", "resume-meaningful-change", "install", "install-resumed"),
    )
    parser.add_argument("--mirror", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if settings.is_production:
        parser.error("Local Shadow is forbidden in production")
    if not args.mirror.is_absolute() or not args.run_dir.is_absolute():
        parser.error("Absolute, external data directories are required")
    repo = Path(__file__).resolve().parents[2]
    if args.run_dir.is_relative_to(repo) or args.mirror.is_relative_to(repo):
        parser.error("Shadow data and budget must stay outside the checkout")
    budget_path = args.run_dir / "provider-budget.json"
    if args.action == "freeze":
        source, cohort = freeze(args.mirror, args.run_dir)
        print(json.dumps({"sourceDigest": source["digest"], "cohortDigest": cohort["digest"], "providerCalls": 0}))
    elif args.action == "initialize-budget":
        # Explicit operator action, never called by run or any child.
        ledger = ProviderBudgetLedger.initialize(budget_path, args.run_id)
        print(json.dumps(ledger.snapshot()))
    elif args.action in {"run", "resume-meaningful-change"}:
        expected = {
            "RARDAR_LLM_RUN_ID": args.run_id,
            "RARDAR_LLM_BUDGET_PATH": str(budget_path),
            "RARDAR_LLM_BUDGET_LIMIT": "40",
        }
        if any(os.environ.get(key) != value for key, value in expected.items()):
            parser.error("Explicit shared budget environment is missing or mismatched")
        if not (args.run_dir / "shadow-review-cohort-manifest.json").is_file():
            parser.error("Freeze the source and cohort before any real calls")
        ledger = ProviderBudgetLedger(budget_path, args.run_id)
        ledger.snapshot()
        route = await resolve_rardar_route_identity()
        runner = resume_meaningful_change if args.action == "resume-meaningful-change" else build_shadow_review
        artifact = await runner(args.mirror, args.run_dir, ledger, route_identity=route)
        if await resolve_rardar_route_identity() != route:
            parser.error("Rardar route changed during Shadow execution; do not install the artifact")
        print(
            json.dumps(
                {
                    "generation": artifact.shadowReviewGeneration,
                    "state": artifact.shadowReviewState,
                    "previewCount": artifact.previewCount,
                    "budget": artifact.providerBudget,
                }
            )
        )
    else:
        artifact = ShadowReviewArtifact.model_validate_json(
            (
                args.run_dir / (ARTIFACT_NAME if args.action == "install-resumed" else "shadow-review-artifact.json")
            ).read_bytes(),
            strict=True,
        )
        if args.action == "install-resumed" and not artifact.reviewable:
            parser.error("Resumed artifact is not reviewable; do not install")
        print(
            json.dumps(
                {
                    "changed": install_shadow(args.mirror, artifact),
                    "generation": artifact.shadowReviewGeneration,
                    "newProviderCalls": 0,
                }
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
