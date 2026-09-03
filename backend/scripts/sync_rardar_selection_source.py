"""Synchronize the bounded Rardar fact bundle used by local Selection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.selection_source import SelectionSourceAdapter, sync_selection_source


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Rardar Observation + Today Selection facts")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--host", default="rardar-prod")
    parser.add_argument("--remote-root", default="/var/lib/rardar/data")
    parser.add_argument("--source-dir", type=Path)
    arguments = parser.parse_args()
    try:
        result = sync_selection_source(
            arguments.target,
            host=arguments.host,
            remote_root=arguments.remote_root,
            source_dir=arguments.source_dir,
        )
        loaded = SelectionSourceAdapter(arguments.target.resolve()).load()
    except Exception as exc:
        print(
            json.dumps({"status": "failed", "code": getattr(exc, "code", "rardar_selection_source_sync_failed")}),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "healthy",
                "sourceObservationSetId": result.source_observation_set_id,
                "captureCount": result.capture_count,
                "sourceWindowStart": loaded.source_window_start,
                "sourceWindowEnd": loaded.source_window_end,
                "todayGenerationId": result.today_generation_id,
                "created": result.created,
                "changed": result.changed,
                "productionWrites": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
