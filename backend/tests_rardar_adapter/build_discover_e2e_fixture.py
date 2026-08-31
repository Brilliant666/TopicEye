"""Build the isolated Playwright Discover projection with a deterministic mock profile provider."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from app.integrations.rardar.discover import DiscoverArtifactAdapter
from app.integrations.rardar.discover_serving import build_discover_serving, install_discover_serving
from tests_rardar_adapter.test_discover import _complete_profiles, _copy_v3_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the isolated Discover E2E fixture")
    parser.add_argument("--target", type=Path, required=True)
    arguments = parser.parse_args()
    # Keep the process-level browser fixture on the newest producer contract.
    # The committed compact v3 artifact is expanded mechanically into its
    # canonical Observation sources before the adapter sees it, so E2E covers
    # the same no-follow, digest, and source-version boundary as real sync.
    with tempfile.TemporaryDirectory(prefix="rardar-discover-e2e-v3-") as temporary:
        source_root = _copy_v3_fixture(Path(temporary))
        discover_source = source_root / "artifacts" / "trending" / "discover" / "v1"
        discover_target = arguments.target / "artifacts" / "trending" / "discover" / "v1"
        if discover_target.exists():
            shutil.rmtree(discover_target)
        shutil.copytree(discover_source, discover_target)
        observations_source = source_root / "observations"
        if observations_source.exists():
            shutil.copytree(observations_source, arguments.target / "observations", dirs_exist_ok=True)

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
