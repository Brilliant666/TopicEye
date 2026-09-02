# 2026-09-02 — Rardar Discover “值得看” Gold Review, Calibration, and Recovery

> Historical iteration record: the normative Product and Output Contracts own
> the final semantics. This record cannot make a prior model or Holdout current.

## Goal

Take over the existing docs-only PR #26 research assets, review the provisional
Gold labels against raw bounded evidence, separate Value from Timeliness, and
measure the simplest compliant model architecture before any Selection Runtime
work begins.

## Baseline and inherited evidence

- TopicEye main: `dfd9045cc6a647d2832b28ae8bb596ddaa630d39`;
- Rardar main: `34556a3ce4765acdc6a91f6fc895846aa33ee5f2`;
- Observation: `trending-v1-20260901T160000Z`;
- Today generation: `20260901T001939007155Z-fe663ec7b844`;
- eligible universe: 461;
- existing bounded sample: 60;
- original provisional Gold: 24;
- old M0 probes: 80 top-level calls.

The inherited worktree and Draft PR head were exact and clean. The task did not
repeat the 60-sample research, recrawl the universe, or rerun the old M0 probe.
Only three bounded public GitHub Evidence Packages were added for new difficult
Holdout samples.

## Gold v2 freeze

All 24 original Gold items were reviewed before model work. Twelve hard samples
were added, producing 36 total projects. Eighteen original projects formed the
Calibration Set; six original boundary projects plus all twelve new samples
formed the 18-item Internal Holdout.

The first freeze exposed a legacy `counterEvidenceRefs` leak into the blind
Value payload. The partial run stopped before item four, its metrics were
discarded, evidence fields were corrected, and the complete metrics were
restarted under final Gold digest:

`68445ccf9306db71aeeb360f544deadd7c6bf67fadaca31ecd3b86dcada85d76`

No label changed after that freeze. Every sample records
`evidenceReviewed=true`, `calibrationReviewed=true`, and
`userReviewed=false`.

## Contract decisions

- Scope, momentum-blind Value, and Timeliness are independent assessments.
- Value payloads contain no stars, rank, growth, momentum, first-seen, Today,
  Observation-window, release-date, or recent-activity facts.
- Primary Reasons are limited to four value reasons and selected by fixed
  precedence; `meaningful_recent_change` becomes a Timeliness concern.
- Strong Timeliness is limited to meaningful release/update, genuinely new
  usable asset, or producer-owned strong recent momentum.
- Ordinary patch releases, pushes, newly observed old repositories, and
  awaiting-Today status are not strong by themselves.
- Semantic decision is a deterministic Scope + Value + Timeliness matrix.
- Duplicate is a publication disposition, not a reject reason.
- Categories use stable English machine enums and record canonical or
  research-derived provenance.

## Real Provider calibration

The existing TopicEye `routing_group=rardar` control plane was used without
changing provider, route, model, base URL, API key, reasoning effort, or
concurrency. New top-level calls were capped at 100; 90 were used with
concurrency 1 and zero cache hits.

M0 remained the inherited baseline. M1 tested blind Value with a model
Timeliness ablation. M2 moved Timeliness facts and final decision to code. M3
added deterministic Primary Reason and peer-context-only duplicate packing.
M3 is the selected architecture.

The Provider returned parseable JSON but did not keep a stable output envelope:
reason/assets/aspects, best-fit, and confidence changed shape. Known variants
were strictly Pydantic-validated and normalized; unknown forms remained
fail-closed. This produced 11/18 structured Holdout successes and one upstream
timeout.

## Holdout result

The final Prompt was frozen before the Holdout, and the Holdout ran exactly
once. Its M3 results were:

- structured success: 11/18 (61.11%);
- evidence validity: 11/11 (100%);
- fabricated claims among validated outputs: 0/11;
- `SELECT_NOW` precision: 1/2 (50%);
- `SELECT_NOW` recall: 1/3 (33.33%);
- `WORTHWHILE_NOT_NOW` accuracy: 6/9 (66.67%);
- high-momentum/low-value false positives: 0/3;
- low-momentum/high-value recall: 2/3 (66.67%);
- scope accuracy: 8/18 (44.44%).

The gates failed. Research completion is still valid; implementation readiness
is not.

## Delivery and scope

Delivered in the same Draft PR #26:

- product model v2;
- output contract v2;
- 36-project normative provisional Gold JSON;
- sample audit and new calibration report;
- platform/adapter semantic clarification;
- repository-external review, freeze, calibration, Holdout, comparison, and
  user-review packets.

Runtime code changed: 0. Frontend changed: 0. Database changed: 0. Migration:
0. Rardar repository changed: 0. Production access/writes: 0/0. No Provider
raw response or secret was committed.

## Structured-output recovery

The follow-up task applied the nine explicit user boundary decisions, producing
Gold v3 with 9 `userReviewed=true` and 27 `userReviewed=false` records. The old
Holdout was downgraded to `historical_revealed_holdout`. Historical persisted
evidence supported a conservative classification of 170 calls: 86 final
structured successes, 80 unknown structured failures, 1 timeout, and 3
diagnostic calls without final-schema assessment.

The selected v3 contract is a minimal Scope/Value Gate over repository-bound
Evidence Aliases using `prompt_json` plus strict local validation. Timeliness is
mostly deterministic; only meaningful release/update uses a separate micro
Schema. Primary Reason and final decision remain deterministic. User-facing
copy is no longer part of the gate.

A 24-project Fresh Holdout with zero overlap against the prior 60, Gold 36, and
per-item probes was frozen before model use and ran once. It achieved 24/24
structured and evidence-valid outputs and passed every frozen semantic and
Provider-repeat threshold. Total new calls were 106/120 at concurrency 1.

Delivered in the same Draft PR #26: the recovery report, sanitized one-use
Fresh Holdout, Gold v3 history, and synchronized product/platform documents.
Runtime/frontend/database/migration/Rardar/Production/model-config changes: 0.

## Stop condition

`READY_FOR_PR26_FINAL_REVIEW = YES`

`READY_FOR_RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01 = NO_UNTIL_PR26_FINAL_REVIEW_AND_MERGE`

The only next action is
`TOPICEYE-PR26-FINAL-CONTRACT-REVIEW-AND-MERGE-01`. PR #26 remains Draft; no
Selection Runtime or Production Discover work starts from this iteration.

## Final contract review closeout

The final review makes the hierarchy, complete confidence branches, protocol
evidence, bounded failure codes, cache identity, ten Known Limitations, and
local/shadow implementation boundary explicit without changing any label or
metric. Once the exact reviewed PR #26 revision is merged, the next independent
task is `RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01` with state
`READY_FOR_LOCAL_SHADOW_IMPLEMENTATION`. Production Discover remains disabled.
