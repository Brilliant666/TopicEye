"""Audit Rardar's current Serving generation for official-narrative fidelity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.integrations.rardar.adapter import RardarArtifactError
from app.integrations.rardar.narrative_fidelity import audit_official_narrative
from app.integrations.rardar.serving import ServingProjectionError


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit one immutable Rardar Serving narrative projection")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = audit_official_narrative(arguments.target)
    except (RardarArtifactError, ServingProjectionError, ValueError):
        print(
            json.dumps({"status": "failed", "code": "rardar_narrative_audit_failed"}, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
