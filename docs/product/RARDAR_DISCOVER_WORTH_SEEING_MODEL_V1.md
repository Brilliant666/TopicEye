# Rardar Discover “值得看” Product Model v3

## Status and evidence basis

This is a docs-only, pre-implementation product contract. It supersedes the
v1/v2 assessment envelope while retaining the existing filename for PR
continuity. It was
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

## Product and authority boundary

| Surface | User question | Authority | Ordering |
|---|---|---|---|
| Today | What has proven 24-hour growth? | Rardar | exact producer rank |
| Discover | What outside Top 20 deserves attention now? | TopicEye over validated Rardar facts | deterministic packing, no public rank |
| Find Project | Which project fits my stated need? | explicit user request | task-specific comparison |
| Deep Insight | What does one project mean in depth? | explicit user request | no collection ordering |

Rardar is authoritative for numeric GitHub identity, Observation windows,
stars, deltas, acceleration, first observation, Today exact facts, Top 20
membership, and source coverage. TopicEye may evaluate bounded same-repository
README, tree, release, canonical Profile, and Rardar facts. It cannot rewrite
producer facts, invent candidates, execute repository code, infer a global
rank, or use model memory as evidence.

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
value strong + timeliness weak or none     -> WORTHWHILE_NOT_NOW
value strong + timeliness uncertain        -> UNCERTAIN
any evidence-integrity failure             -> UNCERTAIN
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

## Category normalization

Category comes from the canonical Project Profile and uses stable English
machine enums with Chinese presentation mapping. When no Profile exists,
research may derive a provisional category, but it must record
`categorySource=research_derived`. No second manually maintained category truth
is allowed.

## Information architecture

The selected page remains one unranked curated stream with category and Primary
Reason filters. A card shows canonical identity, concise Chinese value,
Primary Reason, an explicit why-now only for strong timeliness, product form,
category, and a small producer-owned momentum fact. Momentum is never the
headline or ordering explanation.

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

See [the output contract](RARDAR_DISCOVER_WORTH_SEEING_OUTPUT_V1.md),
[the calibration report](../research/2026-09-02-rardar-discover-worth-seeing-calibration.md),
[the sample audit](../research/2026-09-02-rardar-discover-worth-seeing-sample-audit.md),
and [the provisional Gold Set](../research/data/rardar-discover-worth-seeing-gold-v1.json).
The current recovery evidence is in
[the structured-output recovery report](../research/2026-09-02-rardar-discover-structured-output-recovery.md)
and [the one-use Fresh Holdout](../research/data/rardar-discover-worth-seeing-fresh-holdout-v1.json).
