# 2026-09-02 Rardar Discover “值得看” Sample Audit

> Historical evidence: this audit preserves the review trail and provisional
> labels. Current product and machine semantics come only from the normative
> Product Contract, Output Contract, and Gold JSON.

## Research status

This is a real-data, docs-only product audit. It does not change the current
Discover runtime or activate Production. Gold v3 preserves the complete v1/v2
history. Exactly 9 product-boundary decisions are approved with
`userReviewed=true`; the other 27 remain `userReviewed=false`. Every label is
still provisional.

Source bindings:

- Observation: `trending-v1-20260901T160000Z`;
- Today generation: `20260901T001939007155Z-fe663ec7b844`;
- final eligible universe: 461 numeric GitHub repository IDs;
- bounded research sample: 60 real repositories;
- normative provisional Gold v3: 36 repositories;
- Gold digest: `5a526b7b353b1c5a356545c9e36b7ef717c12f8533b8842699fe8cd48f2797b0`.

No full-universe recrawl or repeated 60-item evidence collection was performed.
The task reused the prior bounded Evidence Packages and added only three
bounded public GitHub packages for difficult Holdout cases.

## Historical Gold v2 design

The 24 original projects were individually re-reviewed before any new model
probe. Twelve difficult projects were added from the same eligible universe:
three high-momentum/low-value boundaries, three strong-value/no-why-now
projects, two low-growth reusable projects, two newly observed mature
projects, and one two-project near-duplicate group.

The split was frozen before model work:

- Calibration: 18 original projects;
- Internal Holdout: 6 original boundary projects + all 12 new projects;
- Holdout executions: exactly one after the final prompt freeze;
- user-approved labels: 0.

## Historical proposed Gold v2

| Group | Repository | Scope | Value | Timeliness | Proposed decision | Primary reason | Review |
|---|---|---|---|---|---|---|---|
| calibration | sapientinc/PRAXIST | in_scope | strong | strong | SELECT_NOW | directly_reusable | change |
| calibration | anomalyco/opencode | in_scope | strong | strong | SELECT_NOW | directly_reusable | keep |
| calibration | github/spec-kit | in_scope | strong | strong | SELECT_NOW | directly_reusable | keep |
| calibration | yamadashy/repomix | in_scope | strong | none | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| calibration | tobi/walgit | in_scope | strong | strong | SELECT_NOW | directly_reusable | change |
| calibration | JuliusBrussee/caveman | in_scope | strong | strong | SELECT_NOW | directly_reusable | keep |
| calibration | koalaman/shellcheck | in_scope | strong | none | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| calibration | treeverse/dvc | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| calibration | hey-api/hey-api | in_scope | strong | none | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| calibration | react/react | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| calibration | d3/d3 | in_scope | strong | none | WORTHWHILE_NOT_NOW | directly_reusable | change |
| calibration | DigitalPlatDev/FreeDomain | in_scope | weak | strong | REJECT | — | keep |
| calibration | b-nnett/grok-bot-0.18-reconstructed | uncertain | weak | none | UNCERTAIN | — | needs_user_decision |
| calibration | vvxw/deploy-vercel | out_of_scope | weak | strong | REJECT | — | keep |
| calibration | Minglink/dsh-infinite-gen-3 | out_of_scope | weak | strong | REJECT | — | keep |
| calibration | flaqai/backlink_skills | uncertain | moderate | weak | UNCERTAIN | — | needs_user_decision |
| calibration | fzakaria/selfdb | in_scope | strong | strong | SELECT_NOW | directly_reusable | needs_user_decision |
| calibration | ApodexAI/FrontierAgent | in_scope | uncertain | strong | UNCERTAIN | — | needs_user_decision |
| holdout | d2lang/d2 | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | change |
| holdout | bryllim/workout-guide | uncertain | strong | strong | UNCERTAIN | — | needs_user_decision |
| holdout | explosion/spaCy | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | change |
| holdout | awesome-dsh-plugin/awesome-dsh-plugin | in_scope | strong | strong | SELECT_NOW | directly_reusable | needs_user_decision |
| holdout | amagine-ai/Amagine3D | in_scope | moderate | strong | UNCERTAIN | — | needs_user_decision |
| holdout | lanicer/cve-2026-41940-PoC | uncertain | moderate | weak | UNCERTAIN | — | needs_user_decision |
| holdout | massgravel/Microsoft-Activation-Scripts | out_of_scope | weak | strong | REJECT | — | keep |
| holdout | iptv-org/iptv | uncertain | moderate | strong | UNCERTAIN | — | needs_user_decision |
| holdout | amirh00sain/SpiderPanel | out_of_scope | weak | strong | REJECT | — | keep |
| holdout | espanso/espanso | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | public-api-lists/public-api-lists | in_scope | strong | none | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | voxel51/fiftyone | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | Eventual-Inc/Daft | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | zealdocs/zeal | in_scope | strong | none | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | flutter/flutter | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | twbs/bootstrap | in_scope | strong | weak | WORTHWHILE_NOT_NOW | directly_reusable | keep |
| holdout | dataelement/dsh-desktop | in_scope | strong | strong | SELECT_NOW | directly_reusable | keep |
| holdout | vibeinging/dsh-desktop | in_scope | strong | strong | SELECT_NOW | directly_reusable | keep |

## Evidence and policy findings

- Value and timeliness must be separate passes with distinct scenes, prompts,
  schemas, and cache identities.
- Value payloads passed a 36/36 deny-list preflight after an initial leakage
  finding caused by legacy Rardar counter-evidence. That partial run was
  discarded, a new Gold digest was frozen, and all metrics restarted.
- `meaningful_recent_change` moved out of value reasons; ordinary patches and
  pushes are not strong why-now evidence.
- Duplicate and not-timely were removed from reject reasons. Semantic decision
  and publication disposition are independent.
- Categories now use stable English machine values and record
  `canonical_profile` or `research_derived` source.

## Historical M3 result

M3 is the selected architecture, not an implementation-ready model. The final
Holdout had 11/18 structured successes, 100% valid refs among successful
outputs, and zero high-momentum/low-value `SELECT_NOW` false positives, but
failed precision, recall, worthwhile, low-momentum recall, scope, and structured
success gates. One call timed out; six other Holdout outputs failed the strict
known-envelope schema.

## Gold v3 and Fresh Holdout status

The controlling task approved the nine former boundary items without changing
the other 27. The former Internal Holdout has been revealed and is retained only
as Development Set evidence. A zero-overlap 24-project Fresh Holdout was frozen
before model use, ran once, and passed every frozen structure, evidence,
semantic, and Provider-repeat gate.

`READY_FOR_PR26_FINAL_REVIEW = YES`

`READY_FOR_RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01 = NO_UNTIL_PR26_FINAL_REVIEW_AND_MERGE`

See [the calibration report](2026-09-02-rardar-discover-worth-seeing-calibration.md)
and [the normative provisional Gold](data/rardar-discover-worth-seeing-gold-v1.json).
See also [the structured-output recovery](2026-09-02-rardar-discover-structured-output-recovery.md)
and [the one-use Fresh Holdout](data/rardar-discover-worth-seeing-fresh-holdout-v1.json).
