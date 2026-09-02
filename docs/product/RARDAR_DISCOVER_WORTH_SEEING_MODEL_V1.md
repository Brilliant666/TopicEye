# Rardar Discover “值得看” Product Model v3

## Status and evidence basis

This is a docs-only, pre-implementation product contract. It supersedes the
v1/v2 assessment envelope while retaining the existing filename for PR
continuity. The v3 contract in this file is the only current product contract;
v1, v2, and M3 references elsewhere are historical evidence only. It was
calibrated against the 2026-09-01 16:00 UTC canonical Observation, Today
generation `20260901T001939007155Z-fe663ec7b844`, a 461-project eligible
universe, 60 bounded Evidence Packages, and a 36-project provisional Gold Set.

Gold v3 digest:
`5a526b7b353b1c5a356545c9e36b7ef717c12f8533b8842699fe8cd48f2797b0`.
All 36 samples remain provisional. Exactly 9 product-boundary decisions are
user-approved and record `userReviewed=true`; the other 27 remain
`userReviewed=false` and are not user-approved production truth.

The product definition is:

> Discover answers “outside Today Top 20, which projects are worth looking at
> now, and why?” It is one unranked, evidence-bound stream, not a momentum
> ranking.

The frozen Fresh Holdout v1 passed every protocol, semantic, and repeat gate.
That makes this contract ready only for a separate final review and merge of
Draft PR #26. The current four-stage runtime remains unchanged; Selection
Runtime implementation and Production activation are not authorized here.

## Normative hierarchy

This file is the **Normative Product Contract**. It owns the Discover product
definition, authority split, Scope, Value, Timeliness, decision, reason,
packing, information architecture, failure semantics, and implementation
boundary. The companion
[Output Contract](RARDAR_DISCOVER_WORTH_SEEING_OUTPUT_V1.md) is the
**Normative Output Contract** for schemas, aliases, validation, retry, failure
codes, and cache identity. The provisional Gold JSON is **Normative Research
Data** for label history and review authority. The one-use Fresh Holdout is
**One-time Evaluation Evidence** only.

Sample audits, calibration reports, recovery reports, and iteration records
are **Historical Evidence**. They explain how the contract was reached but
cannot override either normative contract or make an old model, label version,
or revealed Holdout current again. When documents differ, this product
contract governs product semantics, the Output Contract governs machine
validation, and the Gold JSON governs recorded review history.

## Product and authority boundary

| Surface | User question | Authority | Ordering |
|---|---|---|---|
| Today | Which projects have the greatest verified Star gain over a complete 24-hour window? | Rardar | exact producer rank |
| Discover | What outside Top 20 deserves attention now? | TopicEye over validated Rardar facts | deterministic packing, no public rank |
| Find Project | Which project fits my stated need? | explicit user request | task-specific comparison |
| Deep Insight | What does one project mean in depth? | explicit user request | no collection ordering |

Rardar is authoritative for numeric GitHub identity, Observation windows,
stars, deltas, acceleration, first observation, Today exact facts, Top 20
membership, and source coverage. TopicEye may evaluate bounded same-repository
README, tree, release, canonical Profile, and Rardar facts. It cannot rewrite
producer facts, invent candidates, execute repository code, infer a global
rank, or use model memory as evidence.

Rardar does not own the worth-seeing judgment or page packing. TopicEye owns
Scope/Value and Timeliness assessments, deterministic semantic projection, and
publication packing over validated inputs. Neither TopicEye nor the model may
write back to a Rardar Artifact, Today rank, Star, Observation, or eligibility
fact.

## Three independent assessments

### Scope Assessment

`scopeStatus` is one of `in_scope`, `out_of_scope`, or `uncertain`. Scope asks
whether a public repository has engineering, product, tool, workflow,
learning, knowledge-asset, API, dataset, library, plugin, template, or reusable
capability value for developers and product builders. It does not ask whether
the project is popular or timely.

An out-of-scope project deterministically becomes `REJECT`; uncertain scope
becomes `UNCERTAIN`. Security research, reconstructed assets, vertical content
SDKs, growth-marketing workflows, and rights-sensitive datasets remain
explicit user-review boundaries in Gold v3.

### Momentum-blind Value Assessment

The Value payload must not contain field names or natural-language equivalents
of stars, rank, deltas, growth, momentum, first-seen facts, Today membership,
Observation windows, release dates, or recent activity. Its only inputs are:

- canonical identity and repository name;
- description, language, topics, and license;
- bounded README excerpts and top-level tree;
- canonical Profile fields when available;
- a same-repository short Evidence Alias allow-list and counter-evidence.

`valueVerdict` is `strong`, `moderate`, `weak`, or `uncertain`. The model does
not output `SELECT_NOW` or `WORTHWHILE_NOT_NOW`. High attention cannot upgrade
weak or uncertain value.

### Timeliness Assessment

Timeliness runs after Value and cannot change the Value verdict or reasons.
Most signals are deterministic facts. A model may assess only whether supplied
release notes or bounded revision evidence prove a meaningful release/update.
Missing release notes make an ordinary version tag insufficient.

Strong signals:

- `meaningful_release`;
- `meaningful_update`;
- `genuinely_new_asset`;
- `strong_recent_momentum`.

Weak signals:

- `newly_observed`;
- `recent_activity`;
- `awaiting_today_validation`.

`genuinely_new_asset` requires a recently created or newly delivered repository
and complete usable value evidence. Rardar first observing an old repository is
not genuine newness. A push timestamp alone is not a meaningful update.
Ordinary patches, dependency bumps, spelling fixes, and version-number-only
changes are not meaningful releases or updates. `newly_observed` means only
that Rardar first saw the repository recently; it does not mean the repository
itself is new. `awaiting_today_validation` is a state, not value evidence.

## Structured protocol boundary

The selected mode is `prompt_json` plus strict local JSON parsing, duplicate-key
rejection, closed Schema validation, and Evidence Alias validation. A tiny
`json_schema` capability probe succeeded, but the complete Gate Schema was
rejected by the Provider on 8/8 comparison calls with HTTP 400. `json_object`
returned an unexpected field and remains unknown/unadopted. Therefore neither
the complete Gate nor `prompt_json` is described as native structured output.

## Primary Reason v3

The only value reasons are:

1. `directly_reusable`;
2. `specific_problem_solution`;
3. `distinctive_implementation`;
4. `reference_or_learning_value`.

`meaningful_recent_change` is removed because change belongs to why-now, not
lasting value. The model emits supported `reasonCandidates`; code chooses the
first supported reason in the fixed order above and keeps at most two other
reasons as supporting reasons. This makes Primary Reason independent of array
order and repeat wording.

## Deterministic semantic decision

```text
scope out_of_scope                         -> REJECT
scope uncertain                            -> UNCERTAIN
value weak                                 -> REJECT
value uncertain or moderate                -> UNCERTAIN
value strong + high confidence
  + timeliness strong + high confidence    -> SELECT_NOW
value strong + timeliness strong
  + either confidence below high           -> UNCERTAIN
value strong + timeliness weak or none     -> WORTHWHILE_NOT_NOW
value strong + timeliness uncertain        -> UNCERTAIN
any structure/schema/evidence failure       -> UNCERTAIN
```

AI is not the final decision authority. It supplies bounded assessments; the
matrix above is the only authority. Empty or fewer-than-ten publications are
valid and never filled by stars or a fallback ranking.

## Reject reasons v3

`REJECT` may use at most three of:

- `out_of_product_scope`;
- `no_clear_value`;
- `weak_evidence`;
- `popularity_only`;
- `marketing_only`;
- `not_reusable_or_actionable`;
- `maintenance_or_license_concern`;
- `identity_or_source_invalid`.

`duplicate_of_stronger_candidate` and `not_timely` are removed. Duplication is
a packing fact; a strong project without why-now is
`WORTHWHILE_NOT_NOW`, not a reject.

## Semantic decision and publication packing

`semanticDecision` is separate from `publicationDisposition`:

- semantic: `SELECT_NOW`, `WORTHWHILE_NOT_NOW`, `REJECT`, `UNCERTAIN`;
- disposition: `publish`, `hold`, `suppress_duplicate`,
  `suppress_capacity`, `not_eligible`.

Peer context may establish `nearDuplicateGroup`, product-form differences, and
packing disposition only. It must never support the current project's value.
Each group publishes one item by default; two require evidence of materially
different users, mechanisms, forms, or use cases.

User-facing copy is a later projection. It runs only after
`semanticDecision`, `primaryReason`, Timeliness, and packing are complete.
Copy failure cannot change those fields, trigger a weaker Gate, or refill the
stream.

## Category normalization

Category comes from the canonical Project Profile and uses stable English
machine enums with Chinese presentation mapping. When no Profile exists,
research may derive a provisional category, but it must record
`categorySource=research_derived`. No second manually maintained category truth
is allowed.

## Information architecture

The selected information architecture is `IA_A_SINGLE_CURATED_STREAM`: one
unranked curated stream with category and Primary Reason filters and optional
why-now tags. A card shows canonical identity, concise Chinese value,
Primary Reason, an explicit why-now only for strong timeliness, product form,
category, and a small producer-owned momentum fact. Momentum is never the
headline or ordering explanation.

The stream may contain fewer than ten projects or be empty. It never fills a
quota with low-quality candidates, the next Star-ranked project, or a momentum
fallback.

The detail page reuses the canonical Project Profile and adds one versioned
Selection Context. Find Project, Deep Insight, Action, Watch, and Feedback
remain explicit user actions; viewing a card does not write a user fact.

## AI failure and last-known-good behavior

- Invalid JSON, unknown fields, schema failure, bad Evidence Aliases, timeout, or
  provider failure cannot newly publish a candidate.
- A failed assessment becomes `UNCERTAIN`; it is not replaced by attention.
- Cached/LKG selection is reusable only when the complete evidence, prompt,
  schema, policy, and peer-context digests are identical.
- A changed digest has no LKG entitlement.
- Publication may be smaller or empty while a prior immutable healthy
  generation remains readable.

## Historical M3 result and current readiness

Model v0 had 35% `SELECT_NOW` precision, 100% recall, 0%
`WORTHWHILE_NOT_NOW` accuracy, 66.67% high-momentum/low-value false positives,
and 50% Primary Reason repeat consistency. The main causes were timestamp
interpretation, momentum/value leakage, model-owned final decisions, and
duplicate-as-reject semantics.

Gold v2 has 36 projects: 18 Calibration and 18 Internal Holdout. The single
final Holdout run for M3 produced:

- structured success: 11/18 (61.11%);
- valid evidenceRefs: 11/11 (100%);
- fabricated claims among validated outputs: 0/11;
- `SELECT_NOW` precision: 1/2 (50%);
- `SELECT_NOW` recall: 1/3 (33.33%);
- `WORTHWHILE_NOT_NOW` accuracy: 6/9 (66.67%);
- high-momentum/low-value false positives: 0/3;
- low-momentum/high-value recall: 2/3 (66.67%);
- scope accuracy: 8/18 (44.44%).

Those results are retained as historical failure evidence. The former Holdout
has been inspected and is now `historical_revealed_holdout`; it cannot support
a new blind-test claim. Gate v3 therefore removed user-facing copy and long
evidence references, uses repository-bound Evidence Aliases, computes most
Timeliness signals and every final decision deterministically, and selects
`prompt_json` with strict local parsing, Schema, and evidence validation.

After prompt, Schema, evidence, labels, and policies were frozen, a disjoint
24-project Fresh Holdout ran exactly once. It achieved 24/24 structured and
evidence-valid results, 11/12 SELECT precision, 11/14 SELECT recall, 5/5
WORTHWHILE accuracy, 24/24 scope accuracy, 21/24 value accuracy, and 23/24
Timeliness accuracy. All frozen gates passed. The resulting state is
`MODEL_CONTRACT_READY_FOR_FINAL_REVIEW`, not Selection Runtime approval.

## Final evidence metrics

All metrics retain their numerator and denominator. The v3 Development Set
recorded 36/36 structured success, 32/36 Scope accuracy, 24/36 Value accuracy,
31/36 Timeliness accuracy, 16/36 semantic-decision accuracy, 2/9 SELECT
precision, 2/7 SELECT recall, 10/17 WORTHWHILE accuracy, 1/6 REJECT accuracy,
3/6 UNCERTAIN accuracy, 1/6 high-momentum/low-value false positives, 1/2
low-momentum/high-value recall, and 0/36 fabricated claims.

The one-use Fresh Holdout recorded 24/24 structured success, 24/24 Scope
accuracy, 21/24 Value accuracy, 23/24 Timeliness accuracy, 20/24
semantic-decision accuracy, 11/12 SELECT precision, 11/14 SELECT recall, 5/5
WORTHWHILE accuracy, 0/0 REJECT accuracy (`n/a`), 4/5 UNCERTAIN accuracy, 0/1
high-momentum/low-value false positives, 6/8 low-momentum/high-value recall,
and 0/24 fabricated claims. Provider repeat over eight frozen Development
samples was 8/8 for Scope, 7/8 for Value, 8/8 for reason support, and 4/4 for
meaningful change. Deterministic reason or decision consistency is not
Provider-output consistency.

## Known limitations

1. Fresh Holdout has no REJECT-labelled sample, so REJECT accuracy is `0/0
   (n/a)` rather than evidence of correct rejection.
2. Its high-momentum/low-value boundary has only one sample; 0/1 is weak
   coverage.
3. Development semantic-decision accuracy remains 16/36.
4. Three Fresh Value judgments were too optimistic.
5. One meaningful-release judgment was uncertain.
6. Two medium-confidence Fresh results safely projected to `UNCERTAIN`.
7. Fixed reason precedence intentionally biases results toward
   `directly_reusable`; reason categories are not expected to be balanced.
8. Twenty-seven Gold records still lack item-by-item user confirmation and all
   36 labels remain provisional.
9. Fresh Holdout is now public, `usedOnce=true`, and
   `futureBlindUse=false`; it cannot support a future blind-test claim.
10. `prompt_json` depends on strict local validation and is not upstream-native
    complete JSON Schema enforcement.

These limits are accepted research risks, not solved Production evidence.

## Implementation boundary after PR #26

Merging the exact reviewed PR #26 revision accepts this contract only. The next
independent task is
`RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01`, and its mode must be
`LOCAL / SHADOW MODE FIRST`. Its readiness state is exactly
`READY_FOR_LOCAL_SHADOW_IMPLEMENTATION`, never `READY_FOR_PRODUCTION`.

The implementation must keep Today unchanged, permit an empty publication,
run semantic decision before packing and user copy, and provide no Star,
momentum, model-failure, or capacity refill fallback. It must include a fixed
negative-control set covering `out_of_product_scope`,
`identity_or_source_invalid`, `marketing_only`, `popularity_only`,
`weak_evidence`, and `not_reusable_or_actionable`, none of which may publish as
`SELECT_NOW`. Any future blind-evaluation claim requires a new unseen set.
Production writes, Production Discover activation, and page deployment require
later independent authorization.

See [the output contract](RARDAR_DISCOVER_WORTH_SEEING_OUTPUT_V1.md),
[the calibration report](../research/2026-09-02-rardar-discover-worth-seeing-calibration.md),
[the sample audit](../research/2026-09-02-rardar-discover-worth-seeing-sample-audit.md),
and [the provisional Gold Set](../research/data/rardar-discover-worth-seeing-gold-v1.json).
The current recovery evidence is in
[the structured-output recovery report](../research/2026-09-02-rardar-discover-structured-output-recovery.md)
and [the one-use Fresh Holdout](../research/data/rardar-discover-worth-seeing-fresh-holdout-v1.json).
