"""Build Selection facts from an already verified local Today mirror.

This reads only the fixed current generation and its referenced Observation
copies. It does not scan historical captures, fetch sources or move pointers.
Missing intermediate observations remain honestly degraded in the existing
Selection source contract; they are not a value eligibility gate.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from app.integrations.rardar.adapter import RardarIntelligenceAdapter, _SafeRoot, _strict_json
from app.integrations.rardar.selection_source import (
    BuiltSelectionSource,
    SelectionSourceError,
    _today_references,
    build_selection_source,
)


def build_selection_source_from_today_mirror(target: Path, *, expected_today_generation: str) -> BuiltSelectionSource:
    """Return a validated candidate, without writing any local published data."""
    root = _SafeRoot(str(target))
    root.ensure_available()
    read = root.read_stable
    pointer_raw = read("current.json", maximum_bytes=64 * 1024)
    # Reuse the full fact reader before traversing any pointer-derived path.
    board = RardarIntelligenceAdapter(root).load_explosion_board()
    pointer = _strict_json(pointer_raw)
    if pointer["generationId"] != expected_today_generation or board.generationId != expected_today_generation:
        raise SelectionSourceError(
            "rardar_selection_today_changed", "Today revision changed before Selection preparation"
        )
    prefix = f"generations/{expected_today_generation}"
    manifest_raw = read(f"{prefix}/manifest.json", maximum_bytes=4 * 1024 * 1024)
    explosion_raw = read(f"{prefix}/trending/explosion.json", maximum_bytes=16 * 1024 * 1024)
    explosion = _strict_json(explosion_raw)
    encode = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    generation_files: dict[str, str] = {}
    captures: dict[str, str] = {}
    for reference in _today_references(explosion):
        relative = reference["generationRelativePath"]
        raw = read(f"{prefix}/{relative}", maximum_bytes=16 * 1024 * 1024)
        encoded = encode(raw)
        generation_files[relative] = encoded
        capture_id = reference["captureId"]
        if capture_id in captures and captures[capture_id] != encoded:
            raise SelectionSourceError("rardar_selection_source_invalid", "Observation copies disagree")
        captures[capture_id] = encoded
    candidate = build_selection_source(
        json.dumps(
            {
                "schemaVersion": 1,
                "captures": [{"captureId": key, "content": value} for key, value in sorted(captures.items())],
                "today": {
                    "current": encode(pointer_raw),
                    "manifest": encode(manifest_raw),
                    "explosion": encode(explosion_raw),
                    "generationFiles": generation_files,
                },
            }
        ).encode("utf-8")
    )
    if read("current.json", maximum_bytes=64 * 1024) != pointer_raw:
        raise SelectionSourceError("rardar_selection_today_changed", "Today changed during Selection preparation")
    return candidate
