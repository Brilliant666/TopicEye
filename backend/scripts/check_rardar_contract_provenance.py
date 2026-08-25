#!/usr/bin/env python3
"""Verify vendored Rardar contracts and formal fixture provenance without network access."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CONTRACTS = BACKEND / "app" / "integrations" / "rardar" / "contracts"
FIXTURES = BACKEND / "tests" / "fixtures" / "rardar_intelligence"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    provenance = json.loads((CONTRACTS / "provenance.json").read_text(encoding="utf-8"))
    for contract in provenance["contracts"]:
        actual = digest(CONTRACTS / contract["vendoredPath"])
        if actual != contract["vendoredSha256"] or actual != contract["sourceSha256"]:
            raise SystemExit(f"contract provenance mismatch: {contract['vendoredPath']}")
    for revision in provenance["fixture"]["revisions"]:
        root = FIXTURES / revision["name"]
        generation = root / "generations" / revision["generationId"]
        checks = {
            "currentSha256": root / "current.json",
            "manifestSha256": generation / "manifest.json",
            "explosionSha256": generation / "trending" / "explosion.json",
        }
        for field, path in checks.items():
            if digest(path) != revision[field]:
                raise SystemExit(f"fixture provenance mismatch: {revision['name']} {field}")
    print("Rardar contract and fixture provenance: healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
