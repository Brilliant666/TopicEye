"""Build the isolated Playwright Discover projection with a deterministic mock profile provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.integrations.rardar.discover import DiscoverArtifactAdapter
from app.integrations.rardar.discover_serving import build_discover_serving, install_discover_serving
from tests_rardar_adapter.test_discover import _complete_profiles


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the isolated Discover E2E fixture")
    parser.add_argument("--target", type=Path, required=True)
    arguments = parser.parse_args()
    source = DiscoverArtifactAdapter.from_config(str(arguments.target.resolve())).load()
    built = build_discover_serving(
        source,
        cache_root=arguments.target / "discover-profile-cache",
        profile_provider=_complete_profiles,
    )
    installed = install_discover_serving(arguments.target.resolve(), built)
    print(
        json.dumps(
            {
                "status": "healthy",
                "discoverGenerationId": installed.discover_generation_id,
                "servingGenerationId": installed.serving_generation_id,
                "selectedCount": built.profile_summary.selectedCount,
                "githubRequests": built.profile_result.github_requests,
                "translationCalls": built.profile_result.translation_calls,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
