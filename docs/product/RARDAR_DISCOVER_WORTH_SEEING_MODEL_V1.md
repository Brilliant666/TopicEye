# Rardar Discover “值得看” Product Model v1

## Status and evidence basis

This is a docs-only, pre-implementation product contract. It was derived from
the 2026-09-01 16:00 UTC canonical Observation, the current audited Today
generation, a 461-project eligible universe, 60 stratified real repositories
and 24 provisional Gold decisions. The Gold labels require user review and are
not production truth.

The product definition is:

> Discover answers “outside Today Top 20, which projects are worth looking at
> now, and why?” It is a curated evidence surface, not a momentum ranking.

The current four-stage momentum page remains the implemented runtime until a
separate selection iteration replaces it. This document does not activate
Production Discover.

## Product boundary

Today and Discover solve different jobs:

| Surface | User question | Authority | Ordering |
|---|---|---|---|
| Today | What has proven 24-hour growth? | Rardar | exact producer rank |
| Discover | What outside Top 20 deserves attention now? | TopicEye within Rardar facts | deterministic quality packing; no public rank |
| Find Project | Which project best fits my stated need? | explicit user request | task-specific comparison |
| Deep Insight | What does one project mean in depth? | explicit user request | no collection ordering |

Discover may contain applications, frameworks, libraries, CLIs, Agent Skills,
plugins, APIs, datasets, knowledge assets, starters and workflows. A project
does not need fast star growth to have product value. It does need a defensible
reason to appear now to receive `SELECT_NOW`.

## Authority matrix

Rardar remains the only authority for:

- numeric GitHub repository identity and identity conflicts;
- canonical repository name and URL;
- stars, Observation windows, deltas, acceleration and first observation;
- Today exact facts, rank and published Top 20 membership;
- Capture eligibility, source coverage and momentum facts.

TopicEye may use those facts together with a canonical Project Profile,
README, bounded top-level tree and latest release evidence to:

- decide `SELECT_NOW`, `WORTHWHILE_NOT_NOW`, `REJECT` or `UNCERTAIN`;
- choose one value reason and at most two supporting reasons;
- explain why the project is useful, to whom and why now;
- identify a bounded near-duplicate group;
- classify product form and category.

AI cannot alter Rardar facts, invent candidates or evidence, execute repository
code, emit a score, rank the universe, or treat model knowledge as repository
evidence. Publication is never the model response alone: evidence integrity,
timeliness, confidence, duplicate and packing gates remain deterministic.

## Candidate universe

The eligible set is calculated before any semantic selection:

```text
latest Observation candidates
− Today published Top 20 numeric IDs
− disabled repositories
− identity conflicts
− metadata-incomplete repositories
− unsafe or unbound sources
```

The 2026-09-01 research source produced 500 candidates, 20 Top 20 exclusions,
19 invalid candidates and 461 eligible projects: 459 exact-outside-Top20 and
2 pre-exact. Eligibility is broad recall, not endorsement.

## Decision labels

`SELECT_NOW` means both value and a strong why-now gate are satisfied.
`WORTHWHILE_NOT_NOW` means evidence establishes durable value but not current
timeliness. `REJECT` means a stable rejection reason applies. `UNCERTAIN` means
the evidence package cannot support either a positive or negative decision at
the required confidence.

Empty or fewer-than-ten publications are valid. No branch falls back to stars,
fills a quota, or promotes an invalid result.

## Value reasons

The final Primary Reason enum contains five values:

| Reason | Meaning | Required proof |
|---|---|---|
| `directly_reusable` | A user can adopt a bounded asset now. | concrete package, tool, API, dataset, template or workflow |
| `distinctive_implementation` | The implementation materially differs from ordinary alternatives. | repository-specific architecture or delivery evidence |
| `specific_problem_solution` | It solves a narrow, legible user problem. | problem, mechanism and usable output |
| `reference_or_learning_value` | It is a strong source, corpus, example or guide. | organized, inspectable knowledge assets |
| `meaningful_recent_change` | A recent change itself creates product value. | bounded change or release evidence, not a timestamp alone |

`momentum_signal` is deliberately removed as a value reason. Momentum remains
an auxiliary timeliness fact. Every positive decision has exactly one Primary
Reason and no more than two distinct supporting reasons.

## Timeliness signals

Timeliness is computed before the model call. The model may cite supplied
signals but cannot derive authoritative time buckets from raw timestamps.

| Signal | Deterministic definition | Strength |
|---|---|---|
| `newly_observed` | first canonical observation is at most 4 hours before latest scheduled time | weak alone |
| `recent_release` | non-draft, non-prerelease release is at most 14 days old | strong with value |
| `meaningful_update` | bounded README/tree/release evidence identifies a substantive change at most 7 days old | strong with value |
| `recent_momentum` | Rardar supplies a valid recent delta/acceleration fact | weak alone |
| `recent_activity` | `pushedAt` or `updatedAt` is at most 7 days old | weak alone |
| `awaiting_today_validation` | eligible pre-exact project in a window-eligible Capture | weak alone |

`SELECT_NOW` requires high evidence confidence, a value reason, non-empty
`whyNowZh`, and one of these paths:

1. `recent_release`;
2. `meaningful_update`;
3. `newly_observed` plus `recent_activity`;
4. `awaiting_today_validation` plus `recent_momentum`.

Newness, stars, rank, activity or momentum alone is insufficient. The 60-item
probe showed why: allowing the model to interpret timestamps made mature tools
look newly observed and erased the distinction between `SELECT_NOW` and
`WORTHWHILE_NOT_NOW`.

## Reject reasons

The stable internal enum is:

- `no_clear_value`;
- `weak_evidence`;
- `popularity_only`;
- `marketing_only`;
- `duplicate_of_stronger_candidate`;
- `not_timely`;
- `not_reusable_or_actionable`;
- `maintenance_or_license_concern`;
- `identity_or_source_invalid`.

Reject reasons are audit facts, not public card copy. An identity/source error
also fails the candidate before semantic selection.

## Two-stage selection

### Deterministic broad recall

Recall 30–60 projects from all 461 eligible candidates using only complete
profiles/evidence, product-form coverage, current deterministic timeliness
signals and bounded near-duplicate grouping. Growth can help recall but is not
the final order or value label.

### Evidence-bound semantic selection

Evaluate the recalled set against the strict output contract. Target 10–20
projects, but allow fewer than 10 or an empty publication. A low-confidence or
invalid result is not published. The first implementation must evaluate
near-duplicates with bounded peer context; a single-repository prompt cannot
reliably infer which candidate is stronger.

After quality gates, deterministic packing permits one item per near-duplicate
group by default and two only when evidence establishes distinct use cases.
Category diversity is a tie-break/packing constraint, never a quota or filler
rule.

## AI failure and last-known-good behavior

- Provider failure, invalid JSON, schema failure or invalid evidence reference:
  do not newly publish the candidate.
- Failed candidates do not fall back to stars, momentum, a cached rank or a
  deterministic “top N”.
- A prior healthy selection may be reused only when the complete
  `selectionEvidenceDigest` is identical and the stored result revalidates.
- A changed evidence digest has no LKG entitlement.
- Publication may become smaller or empty while the last healthy immutable
  generation remains readable according to the future serving contract.

## Information architecture decision

Three alternatives were compared:

| IA | Advantage | Failure mode | Decision |
|---|---|---|---|
| A — one curated stream | matches the single user question; reasons and why-now stay on each card | requires strong filtering and duplicate packing | **Selected** |
| B — sections by reason | teaches the taxonomy | projects can fit multiple reasons and sections become arbitrary | not selected |
| C — growth stages | preserves current implementation | reintroduces momentum as the product model | rejected |

IA A has no public numeric rank. It offers category and Primary Reason filters.
Cards show identity, concise `whyWorthSeeingZh`, Primary Reason, `whyNowZh` when
present, category, product form and a small factual momentum indicator. Momentum
never becomes the headline or sort explanation.

The detail page reuses the canonical Project Profile and adds a versioned
Discover Selection Context: decision, reasons, why-now, reusable assets, best
fit, evidence/counter-evidence, timeliness signals, confidence, duplicate group
and selection evidence digest. It does not copy a second profile.

## User workflow

- **Find Project** receives the canonical GitHub project when the user has a
  concrete need; Discover does not pre-fill a comparison claim.
- **Deep Insight** remains an explicit action from the canonical project detail.
- **Action / Watch / Feedback** remain explicit authenticated actions. Viewing a
  Discover card does not write a user fact.
- **Today** keeps exact rank and 24-hour facts unchanged.

## Model comparison and readiness

The provisional Gold Set contains 24 projects: 7 `SELECT_NOW`, 7
`WORTHWHILE_NOT_NOW`, 7 `REJECT` and 3 `UNCERTAIN`. Model A (momentum only),
Model B (value only) and Model C (value plus timeliness) were compared through
TopicEye's existing `routing_group=rardar` route. Model C is the correct product
shape, but the probed prompt is not implementation-ready:

- `SELECT_NOW` precision: 35%;
- `SELECT_NOW` recall: 100%;
- low-growth/high-value recall: 100%;
- high-growth/low-value false-positive rate: 66.67%;
- `WORTHWHILE_NOT_NOW` accuracy: 0%;
- independent repeat decision consistency: 91.67%;
- independent repeat Primary Reason consistency: 50%.

The next implementation iteration must supply deterministic timeliness and
duplicate context, then meet every evaluation gate before Production activation.

See [the output contract](RARDAR_DISCOVER_WORTH_SEEING_OUTPUT_V1.md),
[the sample audit](../research/2026-09-02-rardar-discover-worth-seeing-sample-audit.md)
and [the provisional Gold Set](../research/data/rardar-discover-worth-seeing-gold-v1.json).
