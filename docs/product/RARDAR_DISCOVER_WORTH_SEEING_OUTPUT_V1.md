# Rardar Discover “值得看” Output Contract v3

## Status

This is the **Normative Output Contract** for the v3 Selection Runtime boundary.
It records schemas, aliases, validation, deterministic projection, retry,
failure codes, and cache identity, but adds no runtime code, database schema,
migration, or Production artifact. The Product Model owns product semantics;
historical audits and reports cannot override either normative contract. All
Gold labels remain provisional; exactly 9 of 36 product-boundary decisions are
user-reviewed and the remaining 27 are not.

## Input identity

One assessment is bound to:

```text
githubRepositoryId
candidateUniverseVersion
observation capture ID + digest
Today generation ID + explosion digest
profile/evidence revision
README blob SHA
tree revision
release revision or explicit absence
scope/value/timeliness/reason/packing policy versions
value prompt + schema + scene identity
timeliness prompt + schema + scene identity
near-duplicate context digest
protocol-mode and retry-policy versions
model route identity
```

The canonical digest of those immutable inputs is
`selectionEvidenceDigest`. Numeric GitHub repository ID is identity;
repository name is display data.

The independent version identities are: Scope/Value Prompt, Scope/Value
Schema, Meaningful Change Prompt, Meaningful Change Schema, Reason Policy,
Timeliness Policy, Decision Matrix, Evidence Alias, Packing Policy, Protocol
Mode, and Retry Policy. A cache key includes all of them, the numeric repository
ID, evidence digest, canonical Profile revision, peer-context digest, scene,
and model route identity. Last-known-good reuse is allowed only when the entire
`selectionEvidenceDigest` is exactly equal; README, tree, release evidence,
prompt, schema, policy, protocol, retry, packing, or route changes invalidate
the result.

## Minimal Scope + Value Gate v3

Scope and momentum-blind Value share one small selection-gate call. Every
object has exactly:

| Field | Type and invariant |
|---|---|
| `scopeStatus` | scope enum |
| `valueVerdict` | `strong`, `moderate`, `weak`, `uncertain` |
| `reasonCandidates` | unique evidence-bearing subset of four reason enums |
| `counterEvidenceIds` | same-repository Evidence Alias subset |
| `confidence` | `high`, `medium`, `low` |

The payload and prompt must pass a deny-list test for all popularity,
Observation, Today, ranking, window, delta, momentum, first-seen, release-date,
and recent-activity fields and their natural-language equivalents. It cannot
emit a final decision, why-now, rank, score, growth prediction, duplicate
packing, or user-facing copy. `whyWorthSeeingZh`, `whyNowZh`, reusable assets,
and best-fit copy are separate post-decision outputs and cannot affect the
semantic decision.

The selected research mode is `prompt_json`, not native structured output.
Every response still passes strict JSON parsing, duplicate-key rejection,
closed local Schema validation, alias resolution, and evidence validation.

Capability evidence is deliberately shape-specific: the tiny `json_schema`
probe succeeded, the complete Gate Schema was rejected with HTTP 400 on 8/8
calls, and `json_object` returned an extra field and remains unknown/unadopted.
The formal mode is therefore `prompt_json` with local strict validation; no
document or implementation may claim native complete-Schema enforcement.

## Timeliness result

Most Timeliness signals are computed from verified facts. A separate model
micro-call is made only when bounded release notes or revision-delta evidence
exists. Its complete output is:

| Field | Type and invariant |
|---|---|
| `meaningfulRelease` | `yes`, `no`, `uncertain` |
| `meaningfulUpdate` | `yes`, `no`, `uncertain` |
| `evidenceIds` | subset of the current repository's `T01`… aliases |
| `confidence` | `high`, `medium`, `low` |

`genuinely_new_asset`, `strong_recent_momentum`, and all weak signals are
deterministic. A model may judge `meaningful_release` only when actual release
notes are supplied and `meaningful_update` only when bounded revision evidence
is supplied. If neither exists, no model call is required.

## Deterministic result and packing

The service, never the model, computes:

| Field | Rule |
|---|---|
| `semanticDecision` | fixed Scope + Value + Timeliness matrix |
| `primaryReason` | first supported candidate in fixed v3 precedence |
| `supportingReasons` | at most 2 remaining supported candidates |
| `publicationDisposition` | `publish`, `hold`, `suppress_duplicate`, `suppress_capacity`, `not_eligible` |
| `nearDuplicateGroup` | deterministic/bounded peer comparison only |

The v3 Primary Reason precedence is:

```text
directly_reusable
specific_problem_solution
distinctive_implementation
reference_or_learning_value
```

The reject enum is:

```text
out_of_product_scope
no_clear_value
weak_evidence
popularity_only
marketing_only
not_reusable_or_actionable
maintenance_or_license_concern
identity_or_source_invalid
```

Duplicate and not-timely are not reject reasons. A duplicate may retain
`semanticDecision=SELECT_NOW` with
`publicationDisposition=suppress_duplicate`.

The complete semantic projection is fail-closed:

```text
scopeStatus=out_of_scope                                      -> REJECT
scopeStatus=uncertain                                         -> UNCERTAIN
valueVerdict=weak                                             -> REJECT
valueVerdict=uncertain or moderate                            -> UNCERTAIN
valueVerdict=strong + timelinessVerdict=strong
  + value/timeliness confidence both high                    -> SELECT_NOW
valueVerdict=strong + timelinessVerdict=strong
  + either confidence below high                             -> UNCERTAIN
valueVerdict=strong + timelinessVerdict=weak or none          -> WORTHWHILE_NOT_NOW
valueVerdict=strong + timelinessVerdict=uncertain             -> UNCERTAIN
any structure, schema, source, or evidence-integrity failure -> UNCERTAIN
```

There is no Star, momentum, attention, rank, or next-candidate fallback.

## Evidence Alias contract

Every allow-list entry receives a short `E01`… or `T01`… alias and records its
full evidence reference, source type, source path, source revision, and bounded
excerpt. The model emits aliases only. Local code maps them back after proving
the alias exists and belongs to the same repository, source revision, and
assessment. Timeliness aliases are forbidden from Value; Value aliases cannot
contain momentum facts; peer refs may support packing only and can never prove
current-project value. Cross-repository positive evidence is invalid.

Strict parsing rejects duplicate JSON keys, non-finite numbers, coercion,
unknown fields, unsupported enums, missing required fields, and unbound refs.
Schema normalization must be versioned, bounded to explicit known variants,
and followed by normative model validation.

## Gold v3 review fields

The normative Gold object preserves history and review authority:

```text
originalDecisionV1
originalPrimaryReasonV1
proposedDecisionV2
proposedPrimaryReasonV2
approvedDecisionV3
approvedPrimaryReasonV3
reviewAction
reviewNotes
evidenceReviewed=true
calibrationReviewed=true
userReviewed=true | false
userReviewSource
userReviewVersion
```

`reviewAction` is `keep`, `change`, or `needs_user_decision`. Only the nine
decisions explicitly approved by the controlling task set `userReviewed=true`;
Provider output never changes review authority.

## Retry and failure-code contract

Each assessment permits at most two attempts. The first uses `prompt_json`. The
only retryable error-code enum is:

```text
non_json_output
extra_text_outside_json
json_truncated
missing_required_field
invalid_enum
wrong_field_type
schema_nesting_failure
```

The retry keeps the same evidence, semantic question, model route, prompt and
policy versions, and receives only the stable error code plus a concise Schema.
It never receives the original raw response. The terminal failure-code enum is:

```text
duplicate_json_key
unknown_field
non_finite_number
coercion_required
provider_protocol_rejected
provider_transport_failure
provider_timeout
missing_content
invalid_evidence_alias
cross_repository_evidence
wrong_assessment_evidence
value_momentum_leakage
source_revision_mismatch
retry_exhausted
```

Terminal failures are not retried. A second format failure becomes
`retry_exhausted`. Error codes are bounded operational facts, never permission
for semantic repair, another model, or a fallback ranking.

## Cache and failure behavior

Value and Timeliness have different scene, prompt, schema, and cache identities.
The cache key also includes the full evidence and policy digests. Any source,
policy, schema, prompt, protocol, retry, route, packing, or peer-context change
creates a new key.

Invalid JSON, schema drift, timeout, provider error, invalid aliases, insufficient
confidence, or evidence failure yields `UNCERTAIN` and no new publication.
Protocol, transport, timeout, evidence, and semantic failures are never repaired
by another model or coercion. It never invokes an attention-based fallback. A
prior result may be reused only for an identical complete digest.

## Card and detail projection

Public cards may show canonical identity, bounded Chinese value, localized
Primary Reason, strong why-now, category, product form, and a small
producer-owned momentum fact. They do not show model score, public rank,
confidence, or reject reasons.

The detail route reads the canonical Profile plus a separate versioned
Selection Context keyed by numeric repository ID and immutable Discover
generation. Page-time requests perform no GitHub or model call.

## Readiness gate

Before implementation, the selected v3 contract must pass a truly fresh frozen
Holdout with at least 95% structured success, 100% evidence validity, zero
fabricated claims, 80% `SELECT_NOW` precision, 70% recall, 70%
`WORTHWHILE_NOT_NOW` accuracy, at most 20% high-momentum/low-value false
positives, 70% low-momentum/high-value recall, 80% Provider reason-support
repeat consistency, 85% Provider scope/value repeat consistency, 90% scope
accuracy, 80% value accuracy, and 80% Timeliness accuracy.

Fresh Holdout v1 ran exactly once after the model and label freezes and passed
every gate. The contract is ready for the separate final review of Draft PR
#26. Selection Runtime implementation remains unauthorized until that review
and merge; Production activation remains out of scope.

After the exact reviewed PR #26 revision merges, the only permitted next state
is `READY_FOR_LOCAL_SHADOW_IMPLEMENTATION`. The first implementation must remain
local/shadow, accept an empty publication, preserve Today, and add fixed
negative controls for `out_of_product_scope`, `identity_or_source_invalid`,
`marketing_only`, `popularity_only`, `weak_evidence`, and
`not_reusable_or_actionable`. Production Discover remains disabled and requires
a later independent authorization.

The accepted limitations are normative inputs to implementation: Fresh has no
REJECT label and only one high-momentum/low-value sample; Development decision
accuracy is 16/36; three Fresh Value calls were optimistic; one meaningful
release was uncertain; two medium-confidence results degraded to `UNCERTAIN`;
reason precedence biases `directly_reusable`; 27 Gold items remain unconfirmed;
Fresh is public and cannot be reused as blind evidence; and `prompt_json` relies
on local validation rather than native complete JSON Schema enforcement.
