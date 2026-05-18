"""
Hashing utilities for content fingerprinting.
"""

import hashlib


def content_hash(text: str) -> str:
    """Generate a SHA-256 hex digest for the given text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
