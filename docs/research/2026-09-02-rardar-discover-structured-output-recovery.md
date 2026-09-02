# 2026-09-02 Rardar Discover Structured Output Recovery

> Historical evidence: this report records the pre-final-review recovery run.
> The normative Product and Output Contracts define the current contract and
> take precedence over this report's readiness wording.

## Result

The docs-only recovery task passed. The frozen Fresh Holdout passed every
protocol, semantic, and repeat-consistency gate, so the contract is ready
for a separate final review of Draft PR #26. It does not authorize Selection
Runtime implementation or Production activation.

- conclusion: `MODEL_CONTRACT_READY_FOR_FINAL_REVIEW`;
- new top-level Provider calls: 106/120, concurrency 1;
- selected mode: `prompt_json` (prompt-constrained JSON plus local strict validation);
- Runtime/frontend/database/migration/Rardar/Production changes: 0;
- raw Provider responses committed or persisted by this task: 0.

## Approved product boundaries

Only these nine projects are `userReviewed=true`; all 36 Gold records remain provisional.

| Repository | Approved scope | Approved decision | Disposition |
|---|---|---|---|
| `b-nnett/grok-bot-0.18-reconstructed` | in_scope | UNCERTAIN | hold |
| `flaqai/backlink_skills` | in_scope | UNCERTAIN | hold |
| `fzakaria/selfdb` | in_scope | WORTHWHILE_NOT_NOW | hold |
| `ApodexAI/FrontierAgent` | in_scope | UNCERTAIN | hold |
| `bryllim/workout-guide` | in_scope | UNCERTAIN | hold |
| `awesome-dsh-plugin/awesome-dsh-plugin` | in_scope | WORTHWHILE_NOT_NOW | suppress_duplicate |
| `amagine-ai/Amagine3D` | in_scope | UNCERTAIN | hold |
| `lanicer/cve-2026-41940-PoC` | out_of_scope | REJECT | not_eligible |
| `iptv-org/iptv` | in_scope | UNCERTAIN | hold |

Gold v3 digest: `5a526b7b353b1c5a356545c9e36b7ef717c12f8533b8842699fe8cd48f2797b0`. The other 27 records remain `userReviewed=false`.

## Historical failure classification

The old Holdout has been inspected and is now `historical_revealed_holdout`; it
is not reusable as a blind generalization test. Historical evidence contains
aggregate status and validated projections, but not raw responses or exact
per-call Pydantic paths. Narrow failure subtypes therefore remain unknown instead
of being reconstructed from guesswork.

| Phase | Attempts | Accepted | Transport | JSON | Schema | Evidence | Final | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| M0_existing_baseline | 80 | 80 | 80 | 80 | 72 | 72 | 72 | unknown_structured_failure=8 |
| aborted_momentum_leakage_run | 6 | 6 | 6 | 6 | 0 | 0 | 0 | unknown_structured_failure=6 |
| initial_strict_calibration | 44 | 44 | 44 | 44 | 0 | 0 | 0 | unknown_structured_failure=44 |
| envelope_diagnostics | 3 | 3 | 3 | 3 | n/a | n/a | 0 | none |
| final_calibration | 19 | 19 | 19 | 19 | 3 | 3 | 3 | unknown_structured_failure=16 |
| single_final_revealed_holdout | 18 | 18 | 17 | 17 | 11 | 11 | 11 | timeout=1, unknown_structured_failure=6 |

Across 170 top-level historical calls: 169 returned transport/content/JSON, 86
were schema- and evidence-valid final structures, 80 are
`unknown_structured_failure`, and 1 is `timeout`. Known Value passes account
for 42 calls and the known Timeliness pass for 1; 44 initial strict calls
cannot be safely split by assessment type from persisted evidence. Scope was
embedded in Value and had no independent call.

## Capability probe and selected protocol

| Mode | Tiny probe | Full 8-sample Gate | Interpretation |
|---|---|---|---|
| `json_schema` | supported without fallback | 0/8; Provider 400 | native support is schema-shape dependent and unsuitable for Gate v3 |
| `json_object` | JSON returned but extra field | not advanced | JSON-object mode does not enforce this contract |
| `prompt_json` | supported | 8/8 | selected S1; strict JSON, Schema, and evidence validation remain local |

The probe used three tiny calls, no reasoning effort, no unverified temperature,
and no raw-response persistence. `prompt_json` is not described as native
structured output.

## Gate v3

Scope and Value share one small assessment containing only `scopeStatus`,
`valueVerdict`, `confidence`, evidence-bearing `reasonCandidates`, and
`counterEvidenceIds`. It excludes final decision, Timeliness, duplicate packing,
and all user-facing copy. Evidence is exposed to the model only as `E01`… aliases
and is mapped locally to repository-bound full references. Serialized Value
payload leakage checks found 0 activity/popularity fields or natural-language
equivalents.

Primary Reason uses fixed precedence:

```text
directly_reusable
specific_problem_solution
distinctive_implementation
reference_or_learning_value
```

Only a `supported=true` reason with a valid current-project alias participates.
The final semantic decision remains a deterministic Scope + Value + Timeliness
matrix.

## Timeliness and retry

Repository age, Rardar-owned recent movement, first observation, ordinary
activity, and awaiting-validation state are deterministic. The model receives a
separate `T01`… package only when bounded release notes or revision evidence
exists, and may return only meaningful-release/update enums, confidence, and
aliases. Routine patches are `no`. Development used 12 micro-calls; Fresh used
11. No Fresh format retry was needed.

Each assessment allows at most two attempts. The only retry is format-only for
the seven frozen format errors; evidence and semantic question stay unchanged,
and neither raw output nor another model is used for repair. Protocol rejection,
transport error, timeout, evidence failure, or a second invalid output becomes
`UNCERTAIN`.

## Development Set

The 18-item former Holdout is revealed and joins the 18 Calibration items as a
36-project Development Set.

| Layer | Metric | Result |
|---|---|---|
| protocol | structured final | 36/36 (100.00%) |
| protocol | evidence valid | 36/36 (100.00%) |
| conditional/end-to-end | scope | 32/36 (88.89%) |
| conditional/end-to-end | value | 24/36 (66.67%) |
| conditional/end-to-end | Timeliness | 31/36 (86.11%) |
| conditional/end-to-end | semantic decision | 16/36 (44.44%) |
| end-to-end | SELECT precision | 2/9 (22.22%) |
| end-to-end | SELECT recall | 2/7 (28.57%) |
| end-to-end | WORTHWHILE accuracy | 10/17 (58.82%) |

Provider-repeat results over eight frozen boundary samples:

- scope: 8/8 (100.00%);
- value: 7/8 (87.50%);
- reason support: 8/8 (100.00%);
- meaningful change where applicable: 4/4 (100.00%).

## Fresh Holdout v1

Twenty-four projects were selected from the 461-project eligible universe before
model use. Overlap with the original 60, Gold 36, and prior per-item probes is
0. The set spans 7 categories and
10 product forms without forced label balance.

- label digest: `72aeece7cfb1c12bf0401f4534febbbf79629c5875a7046e8a73731bd26d765d`;
- evidence digest: `7337ef07ef9b9004fb8780782693be2d1358f43ee2c858c39c8f50d91bdaa8f2`;
- model contract digest: `61878b1b8986c71aa00c60a6f4b8656709ed22c8a6d9ed46a5870fd345d36fec`;
- run count: 1; retries: 0;
- status after use: `historical_fresh_holdout_v1`; future blind use: false.

### Protocol and conditional semantics

| Metric | Result |
|---|---|
| Provider accepted | 24/24 (100.00%) |
| Transport success | 24/24 (100.00%) |
| JSON parsed | 24/24 (100.00%) |
| Schema valid | 24/24 (100.00%) |
| Evidence valid | 24/24 (100.00%) |
| Structured final | 24/24 (100.00%) |
| Scope accuracy | 24/24 (100.00%) |
| Value accuracy | 21/24 (87.50%) |
| Timeliness accuracy | 23/24 (95.83%) |
| Primary Reason support | 17/24 (70.83%) |
| Semantic decision | 20/24 (83.33%) |

### End-to-end semantics

| Metric | Result |
|---|---|
| SELECT precision | 11/12 (91.67%) |
| SELECT recall | 11/14 (78.57%) |
| WORTHWHILE accuracy | 5/5 (100.00%) |
| REJECT accuracy | 0/0 (n/a) |
| UNCERTAIN accuracy | 4/5 (80.00%) |
| high-movement/low-value false positive | 0/1 (0.00%) |
| low-movement/high-value recall | 6/8 (75.00%) |
| fabricated claims | 0/24 (0.00%) |

All required Fresh gates passed. `REJECT` accuracy is n/a because evidence-first
sampling produced no REJECT-labelled Fresh item; it is reported rather than
silently assigned 100% and is not one of the frozen readiness thresholds.

Residual semantic errors remain visible: three durable-value judgments were too
optimistic, one release judgment was uncertain, two strong projects received only
medium confidence and therefore projected to UNCERTAIN, and deterministic reason
precedence selected `directly_reusable` more often than the provisional reference
labels. These do not lower the approved thresholds but require attention in final
contract review.

## Artifacts and stop condition

Repository-external sanitized artifacts are under:

`C:\Users\BRILLI~1\AppData\Local\Temp\rardar-worth-seeing-structured-recovery\20260902T093423Z`

They include historical classification, capability probe, development and repeat
results, both freeze manifests, the single Fresh run, three-layer metrics, and the
final recommendation. The repository contains only Markdown, Gold v3, and the
sanitized one-use Fresh Holdout JSON.

`READY_FOR_PR26_FINAL_REVIEW = YES`

`READY_FOR_RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01 = NO_UNTIL_PR26_FINAL_REVIEW_AND_MERGE`

The only next task is
`TOPICEYE-PR26-FINAL-CONTRACT-REVIEW-AND-MERGE-01`.
