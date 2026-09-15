# RARDAR-DAILY-AUDIT-SUMMARY-FIX-01

## Scope

Replace the daily job's two serialized-JSON character cuts with a versioned,
allowlisted summary. No schema migration: `JobExecutionLog.result_summary` is
Text (production information_schema checked separately by Runtime). No business
status, scheduling, budget, retry, content or Find validation changes.

## Contract

- `summarySchema=rardar-daily-audit-v1`, maximum **8192 UTF-8 bytes**, measured
  after complete JSON encoding. Never cut encoded JSON.
- Only operational scalar fields and fixed stage groups are accepted. Full
  profiles, evidence, prompts and model output are excluded.
- Strings normally retain up to160 characters. If necessary the projection is
  regenerated with64 then24 character limits, recording limitedValues; numeric
  counts are not clipped. An impossible bound/encoding failure records an
  explicit auditError without rerunning or relabeling the business result.
- Variable arrays retain at most2 samples with original totalCount and
  omittedCount. The samples are never used as the full failure count.
- auditRound counters describe **current invocation** (resumedRound identifies
  an interrupted round), daily cumulative counters and last-scan snapshot are
  separate. Missing metrics are null, not assumed zero. Reuse is a last-scan
  stock, not summed per slice. Effective slices/sliceLimit are recorded.
- Existing log ID, start/end times and trigger columns remain authoritative.
  Generation and history date/policy references avoid copying full history8.

## Compatibility and failures

Other JobTracker text callers retain their existing contract. Old raw summaries
are returned unchanged with additive summary_info metadata. Invalid JSON is not
repaired; only JSON-looking records exactly2000 characters receive a suspected
legacy-truncation marker. Malformed JSON of other lengths is not called proven
truncation. Admin render does not JSON.parse legacy text.

Material failure catches retain real HTTP status or null, allowed GitHub host
and endpoint category, project ID, and available profile version. Pydantic
diagnostics retain at most4 loc/type samples and total/omitted counts. No error
messages, input/context, URLs with query/userinfo, bodies or credentials.
Diagnostics live beside existing material attempt records. Missing original
model responses and old truncated summaries cannot be recovered by this fix.

## Verification / release

Synthetic tests exercise track_job -> _finish_log -> isolated SQLite Text storage
-> get_recent_logs, legacy reads, Unicode/escaping/bounds, partial vs stage
success, status mapping, timeout/cancel and audit-write lease cleanup. Source and
material tests use existing temp fixtures/mocks; no paid or source calls.
Existing PostgreSQL CI remains the full backend compatibility gate.

Runtime releases only an exact CI-accepted artifact, serially with the separate
Find branch. No migration, production fixtures or manual daily run. Code-only
rollback uses prior images while preserving all audit/business data. New natural
write acceptance is deferred to the next normal09:00/conditional11:00 cycle;
offline tests do not retroactively repair or validate Sep15's truncated records.
