"""Small, allowlisted daily audit projection; never truncate serialized JSON."""

from __future__ import annotations

import json
import math

SUMMARY_SCHEMA = "rardar-daily-audit-v1"
MAX_SUMMARY_BYTES = 8192

# Only operational scalars. No prompts, profiles, response bodies or arbitrary
# exception messages are accepted, even if a caller adds them to its result.
SCALARS = frozenset(
    """
status reason waitReason date roundKind automaticRound targetSourceDate sourceDate
generationId publishedAt count changed sourceRequests providerCalls oldResultPreserved
processed refreshed failed failedAttempts providerRequests visited reused remaining
todayPending historicalPending checked checkedToday checkedHistorical historicalAdmitted
historicalNewAdmitted historicalDailyNewProjectLimit projectSliceLimit providerSliceRequestLimit
failureRetryLimit materialSlices errorCode source acquisitionMode targetPeriodDate
slices sliceLimit
counterScope resumedRound requestedSources
limit policyVersion completedAt startedAt schemaVersion querySuccessCount queryFailureCount
roundSlices configuredSliceLimit roundProviderRequests roundSourceRequests
""".split()
)
GROUPS = frozenset(
    """
materials round cumulative snapshot sources history historyReview publication metadata
targetPeriod counts totals lastSlice materialTotals sourceStates historyReference
""".split()
)


def _project(value: object, omitted: list[int], *, depth: int = 0, text_limit: int = 160):
    if depth > 5:
        omitted[0] += 1
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        if not math.isfinite(value) or abs(value) > 2**63 - 1:
            raise ValueError("audit_numeric_out_of_range")
        return value
    if isinstance(value, str):
        # Operational references only; long values are explicitly incomplete.
        if len(value) > text_limit:
            omitted[0] += 1
        return value[:text_limit]
    if isinstance(value, dict):
        return {
            key: _project(item, omitted, depth=depth + 1, text_limit=text_limit)
            for key, item in value.items()
            if key in SCALARS or key in GROUPS or key in {"github", "trendshift"}
        }
    if isinstance(value, list):
        omitted[0] += max(0, len(value) - 2)
        return {
            "totalCount": len(value),
            "omittedCount": max(0, len(value) - 2),
            "samples": [_project(item, omitted, depth=depth + 1, text_limit=text_limit) for item in value[:2]],
        }
    omitted[0] += 1
    return None


def serialize_daily_summary(result: dict, log_id: int | None = None) -> str:
    modules = result.get("modules") if isinstance(result.get("modules"), dict) else {}
    today = modules.get("today") if isinstance(modules.get("today"), dict) else {}
    audit = result.get("auditRound", today.get("auditRound"))
    # Fixed modules, fixed scalar keys, two source summaries: storage is bounded
    # independently of the number of projects or historic profiles.
    for text_limit in (160, 64, 24):
        omitted = [0]
        summary = {
            "summarySchema": SUMMARY_SCHEMA,
            "logId": log_id,
            "status": _project(result.get("status"), omitted, text_limit=text_limit),
            "date": _project(result.get("date"), omitted, text_limit=text_limit),
            "reason": _project(result.get("reason"), omitted, text_limit=text_limit),
            "auditRound": _project(audit, omitted, text_limit=text_limit),
            "roundMetricsAvailable": isinstance(audit, dict),
            "modules": {
                name: _project(modules[name], omitted, text_limit=text_limit)
                for name in ("today", "historical_review", "historical_hot")
                if isinstance(modules.get(name), dict)
            },
            "scope": "round metrics explicit; legacy material module counters may be cumulative",
            "details": "allowlisted projection; full project lists and content excluded",
            "limitedValues": omitted[0],
        }
        encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) <= MAX_SUMMARY_BYTES:
            return encoded
    raise ValueError("audit_summary_bound_exceeded")


def is_daily_summary(raw: str) -> bool:
    try:
        value = json.loads(raw)
        return isinstance(value, dict) and value.get("summarySchema") == SUMMARY_SCHEMA
    except (ValueError, TypeError, RecursionError):
        return False


def describe_summary(raw: str | None) -> dict:
    """Read-only metadata. Original legacy text is returned separately unchanged."""
    if not raw:
        return {"format": "empty", "complete": None, "truncationSuspected": False}
    try:
        value = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        looks_json = raw.lstrip().startswith(("{", "["))
        return {
            "format": "legacy_invalid_json" if looks_json else "legacy_text",
            "complete": False if looks_json else None,
            # Length and JSON prefix are evidence of the legacy boundary, not
            # proof that missing content can be reconstructed.
            "truncationSuspected": looks_json and len(raw) == 2000,
        }
    return {
        "format": SUMMARY_SCHEMA
        if isinstance(value, dict) and value.get("summarySchema") == SUMMARY_SCHEMA
        else "legacy_json",
        "complete": not (isinstance(value, dict) and bool(value.get("auditError"))),
        "truncationSuspected": False,
    }
