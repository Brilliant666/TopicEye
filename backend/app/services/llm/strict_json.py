"""Strict JSON decoding shared by schema-bound LLM consumers."""

from __future__ import annotations

import json
from typing import Any


class StrictJSONError(ValueError):
    """The model output is not strict, unambiguous JSON."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise StrictJSONError(f"non-finite JSON number is not allowed: {value}")


def _extract_json_text(raw: str | bytes) -> str:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise StrictJSONError("output is not valid UTF-8") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise StrictJSONError("output must be text")

    text = text.strip()
    if not text:
        raise StrictJSONError("output is empty")

    if text.startswith("```"):
        first_line_end = text.find("\n")
        if first_line_end < 0 or not text.endswith("```"):
            raise StrictJSONError("unterminated JSON code fence")
        fence_label = text[3:first_line_end].strip().lower()
        if fence_label not in ("", "json"):
            raise StrictJSONError("unsupported code fence")
        text = text[first_line_end + 1 : -3].strip()
        if not text:
            raise StrictJSONError("output is empty")
    return text


def loads_strict_json(raw: str | bytes) -> Any:
    """Decode one JSON value, rejecting duplicates and non-finite numbers."""
    text = _extract_json_text(raw)
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite,
        )
    except StrictJSONError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise StrictJSONError("output is not valid JSON") from exc
