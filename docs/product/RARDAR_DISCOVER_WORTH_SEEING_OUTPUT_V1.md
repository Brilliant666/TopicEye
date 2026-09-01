# Rardar Discover “值得看” Output Contract v1

## Status

This is a proposed strict contract for a later implementation. It defines the
evidence-bound semantic result and deterministic validation boundary; it does
not add runtime code, a database schema or a Production artifact.

## Input identity

One selection input is identified by:

```text
githubRepositoryId
candidateUniverseVersion
observationCaptureId + digest
todayGenerationId + explosion digest
profile/evidence revision
README blob SHA
tree revision
release revision or explicit absence
timeliness policy version
near-duplicate context digest
```

The canonical SHA-256 of those immutable inputs is
`selectionEvidenceDigest`. Repository name is display data; numeric GitHub ID
is identity.

## Strict result

Every object has exactly these fields. Unknown or duplicate keys, non-finite
numbers, coercion and unbound evidence references are rejected.

| Field | Type | Validation |
|---|---|---|
| `decision` | enum | `SELECT_NOW`, `WORTHWHILE_NOT_NOW`, `REJECT`, `UNCERTAIN` |
| `primaryReason` | enum or null | required for positive decisions; never momentum |
| `supportingReasons` | enum array | at most 2, unique, excluding Primary Reason |
| `whyWorthSeeingZh` | string | concise evidence-backed product value; no global-superlative claim |
| `whyNowZh` | string | mandatory for `SELECT_NOW`; empty for no defensible why-now |
| `reusableAssets` | string array | at most 6 concrete assets |
| `bestFit` | string array | at most 4 evidence-bounded audiences/tasks |
| `distinctiveAspects` | string array | at most 4 repository-specific differences |
| `timelinessSignals` | enum array | supplied deterministic signals only |
| `evidenceRefs` | reference array | non-empty and a subset of the package index |
| `counterEvidenceRefs` | reference array | package-bound negative/uncertainty evidence |
| `evidenceConfidence` | enum | `high`, `medium`, `low`; not a public score |
| `rejectReasons` | enum array | required only for `REJECT`, at most 3 |
| `nearDuplicateGroup` | string or null | bounded group ID, never a similarity score |

The reason, timeliness and reject enums are defined in
[the product model](RARDAR_DISCOVER_WORTH_SEEING_MODEL_V1.md).

This sanitized example is the semantic result projected from the provisional
`d2lang/d2` Gold sample; its references resolve to that sample's Evidence
Package:

```json
{
  "decision": "SELECT_NOW",
  "primaryReason": "directly_reusable",
  "supportingReasons": [
    "specific_problem_solution"
  ],
  "whyWorthSeeingZh": "将文本编译为图表，具备 CLI、编译器、导出器和多种集成，是明确可复用的技术制图工具。",
  "whyNowZh": "v0.8.2 于 8 月 28 日发布；低增长不妨碍近期版本变化带来的查看价值。",
  "reusableAssets": [
    "d2 CLI",
    "diagram compiler",
    "exporters"
  ],
  "bestFit": [
    "架构图和技术文档维护者"
  ],
  "distinctiveAspects": [
    "d2 CLI",
    "diagram compiler",
    "exporters"
  ],
  "timelinessSignals": [
    "recent_release",
    "recent_activity"
  ],
  "evidenceRefs": [
    "rardar:observation:trending-v1-20260901T160000Z:repo:533087958",
    "github:readme:533087958:328e2f69d6a2c6aced5b403c1fc91fedb7cb399f:excerpt:1",
    "github:tree:533087958:0d69dca6f532ceaeacd615d35d1eaa41a238ffdb",
    "github:release:533087958:375881419"
  ],
  "counterEvidenceRefs": [],
  "evidenceConfidence": "high",
  "rejectReasons": [],
  "nearDuplicateGroup": null
}
```

## Cross-field invariants

- `SELECT_NOW` requires high confidence, one Primary Reason, non-empty
  `whyWorthSeeingZh`, non-empty `whyNowZh`, and a valid strong timeliness path.
- `WORTHWHILE_NOT_NOW` requires an established value reason and empty why-now;
  it is not a soft reject.
- `REJECT` requires at least one reject reason. Public payloads need not expose
  that internal reason; its Primary/Supporting Reasons are null/empty.
- `UNCERTAIN` has null Primary Reason and cannot be silently promoted by
  diversity, momentum or quota. Potential value stays explanatory, not a
  selected reason.
- Medium confidence can support `WORTHWHILE_NOT_NOW` or `UNCERTAIN`, not
  `SELECT_NOW`. Low confidence is never published.
- Stars, rank, recent activity, newness and momentum cannot be Primary Reasons.
- All text claims must be supported by the referenced evidence; references do
  not make an unsupported claim valid.

## Evidence reference contract

Every reference index entry carries:

```text
evidenceRef
sourceType
sourcePath
sourceRevision
```

Supported source types are Rardar Observation, Rardar Today explosion,
TopicEye canonical profile, GitHub README blob, bounded GitHub tree and GitHub
release. A reference is valid only when its source digest/revision matches the
Evidence Package and numeric repository ID. Cross-repository links are
counter-evidence unless that other repository is independently admitted as a
candidate with its own package.

## Deterministic fields around the AI result

The selection service, not the model, supplies and validates:

- candidate identity and eligibility;
- Today Top 20 exclusion;
- all star/window/momentum facts;
- all timeliness signal booleans and age thresholds;
- complete evidenceRef allow-list;
- near-duplicate peer context and final group cap;
- category/diversity packing;
- cache identity, versioning and publication manifest.

AI may recommend select/reject and write the bounded explanation. Final
publication is the validated semantic result intersected with deterministic
gates.

## Cache and version identity

The cache key includes the complete `selectionEvidenceDigest`, prompt version,
output schema version, reason/timeliness/reject policy versions and model route
identity. An identical healthy result may be reused. Any evidence, policy or
schema change creates a new key. No stale cache may hide a changed README,
release, profile, Today exclusion or duplicate group.

## Failure behavior

Invalid JSON, duplicate keys, schema mismatch, timeout, provider error, invalid
reference, unsupported claim, low confidence or failed why-now gate produces
`not_selected_this_generation`. It does not produce a deterministic star-based
substitute. An empty generation is valid. Publication is immutable and atomic;
the last healthy generation remains the only LKG boundary.

## Card and detail projection

The public card uses only:

- canonical identity;
- `whyWorthSeeingZh`;
- one localized Primary Reason label;
- `whyNowZh` and bounded timeliness tags when present;
- category and product form;
- a small producer-owned momentum fact.

It does not display a model score, synthetic rank, evidence confidence or
reject reason. The detail route reads the canonical profile and a separate
versioned Selection Context keyed by numeric repository ID and Discover
generation. Evidence can be inspected without a page-time GitHub or model call.

## Versioning

The first implementation must version independently:

```text
worthSeeingOutputSchemaVersion
worthSeeingReasonPolicyVersion
worthSeeingTimelinessPolicyVersion
worthSeeingSelectionPromptVersion
worthSeeingPackingPolicyVersion
```

Changing an enum, age threshold, confidence rule, duplicate cap or publication
gate is a policy change, not an invisible prompt edit.
