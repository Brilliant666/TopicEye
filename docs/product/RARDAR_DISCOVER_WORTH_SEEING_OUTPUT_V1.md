# Rardar Discover “值得看” Output Contract v2

## Status

This is a proposed strict contract for a later Selection Runtime. It records
the calibrated v2 boundary but adds no runtime code, database schema, migration,
or Production artifact. Gold labels remain provisional and user-unapproved.

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
```

The canonical digest of those immutable inputs is
`selectionEvidenceDigest`. Numeric GitHub repository ID is identity;
repository name is display data.

## Scope result

The Scope result has exactly:

| Field | Type |
|---|---|
| `scopeStatus` | `in_scope`, `out_of_scope`, `uncertain` |
| `scopeEvidenceRefs` | non-empty same-repository reference array |
| `counterEvidenceRefs` | same-repository reference array |
| `confidence` | `high`, `medium`, `low` |

Scope is independent of quality, attention, and timeliness.

## Momentum-blind Value result

The Value scene is `rardar_project_profile`. Every object has exactly:

| Field | Type and invariant |
|---|---|
| `scopeStatus` | scope enum |
| `valueVerdict` | `strong`, `moderate`, `weak`, `uncertain` |
| `reasonCandidates` | unique subset of four v2 reason enums |
| `whyWorthSeeingZh` | bounded, evidence-backed Chinese text |
| `reusableAssets` | at most 6 concrete assets |
| `bestFit` | at most 3 bounded audiences/tasks |
| `distinctiveAspects` | at most 4 repository-specific facts |
| `valueEvidenceRefs` | non-empty subset of the same-repository allow-list |
| `counterEvidenceRefs` | same-repository reference subset |
| `confidence` | `high`, `medium`, `low` |

The payload and prompt must pass a deny-list test for all popularity,
Observation, Today, ranking, window, delta, momentum, first-seen, release-date,
and recent-activity fields and their natural-language equivalents. It cannot
emit a final decision, why-now, rank, score, or growth prediction.

The Provider probe observed multiple known JSON envelopes for
`reasonCandidates`, `reusableAssets`, `distinctiveAspects`, `bestFit`, and
`confidence`. A future adapter may strictly validate and normalize an explicit
versioned envelope, but it must reject unknown fields or unsupported types.
The final Holdout's 61.11% structured success means this envelope is not yet
stable enough for implementation.

## Timeliness result

The Timeliness scene is `rardar_explosion_explanation`, with a distinct prompt,
schema, and cache identity. It runs only after Value and has exactly:

| Field | Type and invariant |
|---|---|
| `timelinessVerdict` | `strong`, `weak`, `none`, `uncertain` |
| `strongSignals` | subset of `meaningful_release`, `meaningful_update`, `genuinely_new_asset`, `strong_recent_momentum` |
| `weakSignals` | subset of `newly_observed`, `recent_activity`, `awaiting_today_validation` |
| `whyNowZh` | required only for `strong`; otherwise empty |
| `timelinessEvidenceRefs` | non-empty subset of the timeliness allow-list |
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
| `primaryReason` | first supported candidate in fixed v2 precedence |
| `supportingReasons` | at most 2 remaining supported candidates |
| `publicationDisposition` | `publish`, `hold`, `suppress_duplicate`, `suppress_capacity`, `not_eligible` |
| `nearDuplicateGroup` | deterministic/bounded peer comparison only |

The v2 Primary Reason precedence is:

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

## Evidence reference contract

Every allow-list entry records `evidenceRef`, `sourceType`, `sourcePath`, and
`sourceRevision`. A reference is valid only when its digest/revision and numeric
repository ID match the Evidence Package. Value refs must be same-repository.
Peer refs are a separate field and may support only duplicate grouping and
packing. A cross-repository ref never proves current-project value.

Strict parsing rejects duplicate JSON keys, non-finite numbers, coercion,
unknown fields, unsupported enums, missing required fields, and unbound refs.
Schema normalization must be versioned, bounded to explicit known variants,
and followed by normative model validation.

## Gold v2 review fields

The normative Gold object preserves history and review authority:

```text
originalDecisionV1
originalPrimaryReasonV1
proposedDecisionV2
proposedPrimaryReasonV2
reviewAction
reviewNotes
evidenceReviewed=true
calibrationReviewed=true
userReviewed=false
```

`reviewAction` is `keep`, `change`, or `needs_user_decision`. Codex evidence
review never sets `userReviewed=true`.

## Cache and failure behavior

Value and Timeliness have different scene, prompt, schema, and cache identities.
The cache key also includes the full evidence and policy digests. Any source,
policy, schema, prompt, or peer-context change creates a new key.

Invalid JSON, schema drift, timeout, provider error, invalid refs, low
confidence, or failed why-now validation yields `UNCERTAIN` and no new
publication. It never invokes an attention-based fallback. A prior result may
be reused only for an identical complete digest.

## Card and detail projection

Public cards may show canonical identity, bounded Chinese value, localized
Primary Reason, strong why-now, category, product form, and a small
producer-owned momentum fact. They do not show model score, public rank,
confidence, or reject reasons.

The detail route reads the canonical Profile plus a separate versioned
Selection Context keyed by numeric repository ID and immutable Discover
generation. Page-time requests perform no GitHub or model call.

## Readiness gate

Before implementation, the selected M3 contract must pass the frozen Internal
Holdout with at least 95% structured success, 100% evidence validity, zero
fabricated claims, 80% `SELECT_NOW` precision, 70% recall, 70%
`WORTHWHILE_NOT_NOW` accuracy, at most 20% high-momentum/low-value false
positives, 70% low-momentum/high-value recall, 80% reason consistency, 85%
decision consistency, and 90% scope accuracy.

The 2026-09-02 run failed this gate; Selection Runtime implementation and
Production activation remain blocked.
