"""Rardar Project ID v1, matching upstream pipeline/project_identity.py.

This is the existing cross-repository contract, not a new numeric-ID migration.
Numeric GitHub IDs remain optional external continuity anchors.
"""

import hashlib
import re

REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$")


def canonical_repository(value: str) -> str:
    if not isinstance(value, str) or not REPOSITORY.fullmatch(value):
        raise ValueError("invalid_repository")
    return value.lower()


def project_id_for_repository(value: str) -> str:
    canonical = canonical_repository(value)
    prefix = re.sub(r"[^a-z0-9]+", "-", canonical).strip("-")[:64].rstrip("-")
    return f"{prefix}--{hashlib.sha256(canonical.encode()).hexdigest()[:20]}"
