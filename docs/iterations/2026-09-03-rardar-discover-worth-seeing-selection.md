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
4. Existing cached canonical profiles form a bounded Evidence Package. On a
   profile cache miss, Selection uses deterministic evidence extraction and
   never issues an uncounted profile-model call. Missing README/tree/release
   evidence may use at most four GitHub requests per project. Repository content
   is untrusted and never executed.
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
   Full validation precedes atomic pointer activation; corrupt data fails
   closed, and retained generations can be explicitly rolled back.

## Identity and idempotence

The Selection input digest binds source capture IDs/digests, source and Today
generations, Today Top 20 set, candidate universe, evidence-cache inventory,
recall limit, every contract version, protocol mode and a secret-free model
route fingerprint. The model route is checked again before publication. An
unchanged rebuild returns `changed=false` with zero GitHub/model calls and
preserves pointer bytes.

## Serving and product

`GET /api/v1/rardar/discover/selection` returns local `mode=shadow` with
`ready`, `empty`, `stale`, `not_configured` or `invalid`. Project detail is
generation-bound. Both collection and detail read only static Serving files,
support ETag/304 and perform no GitHub/model calls, raw reads or business
writes.

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
  `UNCERTAIN`/missing copy without popularity fallback.

## Verification and operations

The isolated suite covers universe/exclusion, six-channel recall, leakage,
aliases, retry, decision matrix, timeliness, negative controls, duplicate and
capacity packing, empty publication, input identity, atomic activation,
rollback, corruption, unsafe paths, ETag/304 and zero raw request-time reads.
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
