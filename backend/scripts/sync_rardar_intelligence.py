"""CLI for a read-only Production-to-local Rardar Artifact sync."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.sync import RardarSyncError, sync_rardar_intelligence
from scripts.rebuild_rardar_serving import real_profile_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync one verified Rardar generation into a local mirror")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--host", default="rardar-prod")
    parser.add_argument("--remote-root", default="/var/lib/rardar/data")
    parser.add_argument("--translate-top", type=int, default=20, choices=range(0, 21), metavar="0..20")
    parser.add_argument("--generate-profiles", action="store_true", help="Explicitly allow model enrichment")
    arguments = parser.parse_args()
    try:
        if arguments.generate_profiles:
            from app.services.llm.provider_budget import ProviderBudgetError, execution_budget

            if execution_budget("rardar_project_profile") is None:
                raise ProviderBudgetError("provider_budget_missing")
        result = sync_rardar_intelligence(
            target=arguments.target,
            host=arguments.host,
            remote_root=arguments.remote_root,
            profile_provider=real_profile_provider(
                translate_top=arguments.translate_top, allow_model_generation=arguments.generate_profiles
            ),
        )
    except RardarSyncError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as exc:
        code = getattr(exc, "code", "rardar_sync_serving_failed")
        print(json.dumps({"status": "failed", "code": code}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({"status": "healthy", **result.__dict__}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
