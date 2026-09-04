# 2026-09-03 — Rardar Discover “值得看” Local Shadow Selection

## Goal and boundary

This iteration implements the accepted PR #26 product contract as a local-only
Shadow runtime. Discover answers “Today Top 20 之外，哪些项目值得现在花时间点开？”
It is not rank 21–N, a growth board, an AI score or a replacement for Rardar
fact authority. Production Discover stays disabled; Today artifacts, Serving,
ranking, identity, profiles and UI are unchanged.

No PostgreSQL business table or migration was added. Existing LLM control-plane
logs/cache are the only permitted database writes. Real Selection artifacts and
provider responses live outside Git under
`%LOCALAPPDATA%\TopicEye\rardar-intelligence\discover-worth-seeing`.

## Pipeline

1. A dedicated source synchronizer verifies an immutable 26–72 hour Rardar
   Observation inventory and authoritative Today published set without
   requiring Production Discover. Its vendored capture contract is pinned to
   Rardar `34556a3` and accepts only the producer's versioned 45- or 90-day
   raw-retention values. Hash validation completes before its pointer switches.
2. The candidate universe is the latest eligible Observation capture minus
   Today published Top 20 and invalid/incomplete identities. Exact rank 21+
   remains eligible.
3. Six independent deterministic channels recall 30–60 projects. Momentum-only
   recall is capped at 40%; no aggregate score is calculated.
4. An evidence-content Profile Cache v2 separates reusable semantic content
   from the current Observation/Selection projection. Equivalent healthy
   profiles are rebound with zero GitHub/profile-model calls; a true miss uses
   the existing profile builder. The original in-memory 120-call counter was
   not a cross-process execution bound; see the convergence correction below.
   Missing README/tree/release evidence may use at most four
   GitHub requests per project. Repository content is untrusted and never
   executed.
5. The `routing_group=rardar` Scope/Value Gate sees only repository-bound `E##`
   aliases. The serialized payload is momentum-blind and uses `prompt_json`
   with strict parse, Schema and alias validation. Only format failures may be
   retried once.
6. Timeliness is deterministic except for bounded meaningful release/update
   assessment over `T##` evidence. Ordinary patch/dependency/version-only work
   is not a meaningful change.
7. A fixed matrix produces `SELECT_NOW`, `WORTHWHILE_NOT_NOW`, `REJECT` or
   `UNCERTAIN`. Program precedence chooses the primary reason. The model never
   owns either result.
8. Duplicate suppression and capacity are publication dispositions, not value
   verdicts. Eligible reason queues are packed by fixed round-robin with no
   public rank. User copy runs only after packing and cannot change selection.
9. Raw and public-safe Serving files are hash-bound in an immutable generation.
   `current` names the last healthy `ready` or fully assessed `empty`
   generation; `latest-attempt` may expose a `degraded` recovery without
   replacing it. Full validation precedes atomic pointer activation; corrupt
   data fails closed, and retained healthy generations can be explicitly rolled
   back.

## Identity and idempotence

The Selection input digest binds source capture IDs/digests, source and Today
generations, Today Top 20 set, candidate universe, evidence-cache inventory,
recall limit, every contract version, protocol mode and a secret-free model
route fingerprint. Profile content identity excludes Observation generation,
Star/rank/momentum and timestamps; its projection binding carries the current
repository, evidence aliases and Selection provenance. The model route is
checked again before publication. Only an unchanged healthy generation is a
permanent no-op. Retryable profile failures use a separate append-only attempt
ledger with bounded backoff, while a degraded result without a retry deadline
is rebuilt rather than frozen by the prior input digest.

## Serving and product

`GET /api/v1/rardar/discover/selection` returns local `mode=shadow` with
`ready`, fully assessed `empty`, `degraded`, `stale`, `not_configured` or
`invalid`. A degraded latest attempt returns safe coverage diagnostics and the
last healthy items when available; it never masquerades as an empty result.
Project detail is generation-bound. Both collection and detail read only static
Serving files, support ETag/304 and perform no GitHub/model calls, raw reads or
business writes.

The local `/discover` page is one unranked stream. Category and primary-reason
filters persist in the URL without reordering. Cards expose value before
auxiliary momentum, support whole-card pointer/keyboard navigation, and keep
the GitHub action independent. Detail reuses the canonical profile and adds a
versioned Selection context plus Find Project prefill.

## Security and failure semantics

- canonical GitHub URLs reject credentials, query/fragment confusion and path
  mismatch;
- aliases cannot cross repositories or evidence classes;
- links, junctions, reparse points, traversal, unstable reads, extra files and
  digest mismatches fail closed;
- prompt injection, HTML/script noise and oversized responses are rejected;
- provider secrets, prompts and raw responses are absent from artifacts,
  Serving, errors and logs;
- six fixed negative controls cannot produce `SELECT_NOW`, and out-of-scope is
  always `REJECT`;
- individual model, GitHub or copy failures degrade to bounded
  `UNCERTAIN`/missing copy without popularity fallback; repeated retryable
  profile failures are classified with safe public codes and cannot overwrite
  a healthy profile.

## Verification and operations

The isolated suite covers universe/exclusion, six-channel recall, leakage,
aliases, retry, decision matrix, timeliness, negative controls, duplicate and
capacity packing, evidence-content identity, cross-generation rebind, V1 safe
migration, negative-cache recovery, ready/empty/degraded activation, atomic
pointer rollback, retained-v1 compatibility, corruption, unsafe paths,
ETag/304 and zero raw request-time reads.
Frontend unit and production-build Playwright cover the single stream,
filters/history, independent actions, detail, empty/stale/invalid states and
375/768/1440 layouts.

Local commands:

```powershell
.\scripts\rardar-local.ps1 build-selection
.\scripts\rardar-local.ps1 selection-status
.\scripts\rardar-local.ps1 rebuild-selection
.\scripts\rardar-local.ps1 selection-rollback -SelectionGeneration <id>
```

The implementation PR may merge only after real local Shadow acceptance,
exact-head CI and self-review. After merge, the dedicated local Runtime is
updated and rebuilt for user review. Production activation, Watchlist,
Candidates, Activity and external signal probes remain separate future tasks.

## 2026-09-04: local Shadow convergence correction

Task: `RARDAR-DISCOVER-SHADOW-CONVERGENCE-01`, continuing PR #28. The 41/48
profile recovery is useful existing evidence, not full readiness. The remaining
seven failures stay unchanged. No new profile generation is authorized.

The previous recovery made 383 distinct Provider executions because per-build
memory accounting did not cover the entire task, retries and restarted scripts.
This is recorded as a historical execution error, not hidden in a new counter.
The newly authorized 40 attempts have one durable, cross-process ledger,
pre-dispatch reservation, no refunds, explicit initialization and no implicit
child-ledger creation. Both successful and failed attempts consume the same
budget; cached results and local validation do not.

The new contract freezes `shadow-review-cohort-v1` from qualified existing
profiles, uses accepted Selection judgments unchanged, and writes a distinct
immutable Shadow Review Artifact plus independent local pointer. Full state
remains degraded. A terminal 16/16 cohort can be reviewable with 0–6 preview
cards; copy failures hide text without changing membership. Partial or corrupt
results are not reviewable. The local API flag cannot enable this in Production.

Implementation and tests cover multi-process budget exhaustion, interrupted
reservations, route retry accounting, cache hits, deterministic cohort coverage,
freeze conflicts, immutable serving, pointer rollback, no full-current writes,
copy-failure membership, zero-select and UI status/filters. Fresh/repeat existing
migrations run only against an isolated PostgreSQL database. The code adds no
DB model, migration, scheduler, provider/model configuration or new product IA.

The run's source/cohort manifests, complete 16-row decisions, unresolved attempt
history, ledger, exact-head browser evidence and final acceptance packet remain
outside Git. Their actual results are attached to PR #28 after execution; this
document does not pre-claim real gate, merge, runtime activation or Production
readiness. See [the adapter contract](../platform/RARDAR_DISCOVER_ADAPTER.md#bounded-local-cohort-review-2026-09-04)
for explicit commands, state semantics and rollback boundaries.

## 2026-09-04: Meaningful Change invocation-binding correction

The first real cohort reached 16 terminal assessments, with six completed
controls and one interrupted Scope attempt, but all six release-only change
requests failed the unchanged evidence-type guard. The sole ledger remained
28 attempted / 27 completed / one interrupted, limit 40. This is an incomplete
review, not evidence that no worthwhile projects exist. The zero-call audit
found missing explicit kind/alias/source-type constraints; rejected structured
responses were not retained, so none can honestly be reconstructed or replayed.
No cache cross-scene collision or model-disobedience claim is inferred.

The authorized PR #28 correction adds explicit repository/evidence/route-bound
assessment context and cache identity. Only the Meaningful Change prompt moves
to v4; the four-field response schema remains v3 and the T-alias namespace stays
v1. Scope/Value, User Copy wording, decision matrix and primary reasons do not
change. The exact source/cohort and all old receipts are preflighted before
dispatch. Six previously failed change stages may each consume one new attempt;
Copy may consume one per actual Preview. No automatic retry, second ledger,
profile recovery, repeated Scope/control call, or replacement candidate exists.

New versioned receipts and an independently identified artifact preserve the
original incomplete result. Normalized Schema fields are retained for strict
local replay; raw Provider responses and prompts are not. Each accepted change
is revalidated; rejected requests are counted separately. Four same-kind
failures block with the specific evidence-binding code, while an isolated
failure remains terminal `UNCERTAIN`. Production remains disabled and Today
is unchanged. The final exact-head test, real recovery, browser, merge and
Runtime evidence belongs in the external run packet and PR body, not a
pre-claimed PASS here. See the [recovery contract](../platform/RARDAR_DISCOVER_ADAPTER.md#meaningful-change-evidence-binding-recovery).
