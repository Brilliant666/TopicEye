"""Write a machine-readable semantic audit for the current Rardar Serving Top 20."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.content_quality import audit_serving_top20
from app.integrations.rardar.serving import ServingProjectionError


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit current Rardar Serving Top 20 content quality")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = audit_serving_top20(arguments.target)
    except (OSError, ValueError, ServingProjectionError):
        print(json.dumps({"status": "FAIL", "code": "rardar_serving_content_audit_failed"}), file=sys.stderr)
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
