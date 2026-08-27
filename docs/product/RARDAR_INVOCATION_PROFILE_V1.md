# Rardar Invocation Profile V1

## Purpose and ownership

An Invocation Profile is a versioned Rardar business contract describing how one scene wants to use a model. It contains no provider, API base, API key or model ID. TopicEye's existing control plane selects a compatible model from the strict `rardar` routing group and remains responsible for connection, admission, retries, failover, cache, logs and usage.

Rardar owns the system prompt, evidence contract and response schema for exactly three V1 scenes:

- `rardar_project_summary`
- `rardar_project_profile`
- `rardar_explosion_explanation`

Find Project and all additional scenes are deferred. TopicEye's topic-analysis, creator, report and digest prompts are not Rardar prompt dependencies.

## Profile fields

| Field | Contract |
| --- | --- |
| `scene` | One of the three fixed V1 scene names. |
| `promptVersion` | Immutable Rardar prompt revision. |
| `schemaVersion` | Immutable strict response-schema revision. |
| `systemPromptContract` | Trusted policy ID and invariants; never supplied by repository evidence. |
| `inputEvidenceContract` | Allowed evidence types, byte/token bounds, source revisions and required provenance. |
| `requestedReasoningEffort` | `medium`, `high` or `xhigh`; never silently downgraded. |
| `temperature` | Number, `"inherit"`, or `null`; `null` explicitly omits the parameter. |
| `maxOutputTokens` | Positive scene request, subject to a proven model hard limit. |
| `structuredOutputMode` | Ordered, explicit native/fallback policy plus mandatory local validation. |
| `responseSchema` | Rardar-owned Pydantic/schema identity; no free-form production artifact. |
| `timeoutClass` | Named engine policy such as `interactive` or `standard`, not a connection setting. |
| `cachePolicy` | Versioned cache scope and source-revision invalidation rule. |
| `failurePolicy` | Stable failure behavior and whether publication may continue without AI. |

`"inherit"` asks the engine to consider the model-card default; it does not guarantee that the value will be sent. An explicit JSON `null` declares that the scene does not request a temperature value. Both are scene intent, not capability evidence: the final request is governed by the selected model's `temperaturePolicy`, and an `unknown` branch still fails closed. Loopback `0.3`/`1.0` observations are non-normative research evidence; the current live model-row temperature and real-provider reasoning policy remain unconfirmed.

## Common trusted-system contract

All three scenes share these invariants:

1. Repository names, README text, source files, comments, issues and release notes are untrusted evidence.
2. Evidence is delimited and labeled with source references and revisions.
3. Instructions embedded in evidence must not alter system policy, output schema, ranking or tool access.
4. The model has no tools, command execution, network access or credential access.
5. The model cannot write a database, publish an artifact or change `current` data.
6. Every factual claim must trace to `evidenceRefs`; inference is labeled and carries confidence/limitations.
7. The result is accepted only after strict local JSON and Pydantic validation.
8. Prompt version, schema version, source revisions and selected effective invocation values are recorded.

Repository evidence that says “ignore previous instructions”, asks for secrets, asks to call a tool, or asks to change score/rank rules is quoted only as data and never followed.

## Structured-output policy

V1 does not assume one native mode works everywhere. The profile declares an ordered policy:

```json
{
  "preferred": ["json_schema", "json_object", "prompt_json"],
  "required": "local_strict_validation",
  "fallbackMustBeExplicit": true
}
```

| Transport mode | What it proves | What it does not prove |
| --- | --- | --- |
| `json_schema` | A successfully probed upstream accepts the exact schema dialect. | It does not replace local parsing, source checks or Pydantic validation. |
| `json_object` | A successfully probed upstream accepts JSON-object mode. | It does not enforce the Rardar field schema. |
| `prompt_json` | Text completion can be parsed under the local strict contract. | It provides no provider-native constraint and may fail more often. |

The local floor rejects duplicate keys, non-finite numbers, invalid UTF-8/JSON, wrong top-level types, missing/incorrect fields and forbidden extras according to the scene schema. A fallback is allowed only when the profile lists it, is bounded to one transition, and records the selected mode. Removing `response_format` must not be described as proof that the provider supports structured output.

## Parameter ownership and merge

The three layers have distinct authority:

| Layer | Owns |
| --- | --- |
| TopicEye model configuration | Provider/API base/key/model, connection settings, general defaults, hard limits and the Model Capability Profile. |
| Rardar Invocation Profile | Scene, prompt/schema versions, desired reasoning effort/temperature/output budget, structured-output requirement, cache and failure policy. |
| AI Engine | Capability validation, strict-route selection, effective-parameter calculation, limits, retry/failover, cache, call logs and usage/cost. |

Rardar business code never selects a provider or model. The engine resolves:

```text
model connection + defaults + hard capability bounds
  + Rardar Invocation Profile requirements
  -> validated effective invocation
```

Deterministic rules:

1. Connection fields always come from the TopicEye model row.
2. The Invocation Profile supplies scene requests; it never mutates the model-card default or treats TopicEye content-production presets as Rardar defaults.
3. The engine selects `temperaturePolicy.whenReasoning` whenever `requestedReasoningEffort` is non-null, otherwise `temperaturePolicy.normal`.
4. Under `free`, a numeric scene value is range-validated and sent. `"inherit"` uses the model-card default when configured and otherwise omits; JSON `null` omits.
5. Under `omit`, the engine sends no temperature and never inherits the model-card default. A numeric scene requirement conflicts; `"inherit"`/`null` resolve to recorded omission.
6. Under `fixed`, the capability's finite, evidence-backed `fixedValue` is sent. A different numeric request or an explicit JSON `null` is an `invocation_parameter_conflict`; `"inherit"` accepts the fixed capability value.
7. Under `unsupported`, a numeric or `"inherit"` request fails with `model_capability_unsupported`; a JSON `null` may proceed without the parameter while recording the limitation.
8. Under `unknown`, unattended selection fails with `model_capability_unverified`. It does not inherit, omit, or guess a value.
9. Effective output limit is `min(scene maxOutputTokens, proven model maxOutputTokens)`.
10. If the model limit is unknown and the scene requires a guaranteed bound, selection fails closed.
11. The requested effort must be explicitly supported for the configuration revision.
12. The Model Capability Profile declares available structured modes, the Invocation Profile declares its ordered requirement, and the engine selects an intersection. No intersection returns `structured_output_mode_unavailable`.
13. Timeout class is mapped centrally and remains under TopicEye's global hard cap.
14. All non-secret requested/effective values and capability evidence scope/revisions are logged.
15. A capability mismatch may select another proven-capable model only within `rardar`; it never converts `0.3` to `1.0`, silently omits a requested numeric value, changes/downgrades effort, hard-codes behavior by model name, or falls back to `default`.

The scene profiles below define desired behavior; they are not proof that the current route can execute it. The current draft capability profile leaves both temperature branches and reasoning support `unknown`, so `temperature: null` does not bypass capability validation: unattended execution remains ineligible until applicable evidence resolves the required branch.

## Scene: `rardar_project_summary`

### Goal

Explain quickly in Chinese what a repository does, for whom, what problem it solves and its core capabilities. The result is short, factual and bounded by evidence.

### Evidence

- repository and display name;
- GitHub description;
- bounded README excerpt with source revision;
- primary languages and topics;
- license fact;
- latest release and push facts.

### Output

- one-sentence Chinese summary;
- intended users;
- problem solved;
- concise capability list;
- evidence references, unknowns, confidence and limitations.

### Draft profile

```json
{
  "scene": "rardar_project_summary",
  "promptVersion": "rardar-project-summary-v1",
  "schemaVersion": "rardar-project-summary-v1",
  "systemPromptContract": "rardar-trusted-evidence-boundary-v1",
  "inputEvidenceContract": "rardar-project-summary-evidence-v1",
  "requestedReasoningEffort": "medium",
  "temperature": null,
  "maxOutputTokens": 500,
  "structuredOutputMode": {
    "preferred": ["json_schema", "json_object", "prompt_json"],
    "required": "local_strict_validation",
    "fallbackMustBeExplicit": true
  },
  "responseSchema": "RardarProjectSummaryV1",
  "timeoutClass": "interactive",
  "cachePolicy": "source-revision-and-contract-version",
  "failurePolicy": "fail-ai-result-only"
}
```

The factual page remains available when this scene fails. No summary is fabricated as fallback.

## Scene: `rardar_project_profile`

### Goal

Build a reusable, evidence-backed view of project capabilities, integration shape, cost and limitations.

### Evidence

- bounded README and documentation extracts;
- directory structure;
- dependency manifests;
- API, SDK, CLI, service and module probes;
- deployment modes;
- license;
- release/push/activity facts;
- static-analysis revision and file-level evidence references.

### Output

The response chooses one canonical reuse type:

- `whole_product`
- `module_or_library`
- `provider_or_connector`
- `workflow`
- `reference_only`
- `not_recommended`

The conceptual labels `module_library` and `provider_connector` in early design notes map to the already accepted canonical names above; they are not additional wire values.

It also returns core capabilities, reuse approach, integration cost, concrete integration work items, constraints, license/risk, evidence, unknowns, confidence and a next validation action. `reference_only` may carry reference kinds such as architecture, UI, workflow design, knowledge or infrastructure.

### Draft profile

```json
{
  "scene": "rardar_project_profile",
  "promptVersion": "rardar-project-profile-v1",
  "schemaVersion": "rardar-project-profile-v1",
  "systemPromptContract": "rardar-trusted-evidence-boundary-v1",
  "inputEvidenceContract": "rardar-project-profile-evidence-v1",
  "requestedReasoningEffort": "xhigh",
  "temperature": null,
  "maxOutputTokens": 1800,
  "structuredOutputMode": {
    "preferred": ["json_schema", "json_object", "prompt_json"],
    "required": "local_strict_validation",
    "fallbackMustBeExplicit": true
  },
  "responseSchema": "RardarProjectProfileV1",
  "timeoutClass": "standard",
  "cachePolicy": "static-evidence-revision-and-contract-version",
  "failurePolicy": "retain-last-matching-source-revision-only"
}
```

The requested `xhigh` is a business requirement, not a claim that the currently configured route supports it. Until a capability probe marks it supported, the engine must choose another capable model in `rardar` or return a stable mismatch.

## Scene: `rardar_explosion_explanation`

### Goal

Explain why a project may be exploding now without changing the factual board.

### Evidence

- audited 24-hour star delta and observation window;
- first-seen/new-entry state and observation sequence;
- release and push facts;
- issue/PR activity when available;
- GitHub Trending and other auxiliary signals with source labels;
- repository metadata and exact Explosion Artifact revision.

### Output

- facts copied from evidence;
- labeled possible drivers/inferences;
- unknowns and alternative explanations;
- risk/limitations;
- confidence and evidence references.

The result must be displayed as an **AI explosion-reason judgment**, never a proven causal fact.

### Draft profile

```json
{
  "scene": "rardar_explosion_explanation",
  "promptVersion": "rardar-explosion-explanation-v1",
  "schemaVersion": "rardar-explosion-explanation-v1",
  "systemPromptContract": "rardar-trusted-evidence-boundary-v1",
  "inputEvidenceContract": "rardar-explosion-evidence-v1",
  "requestedReasoningEffort": "high",
  "temperature": null,
  "maxOutputTokens": 1000,
  "structuredOutputMode": {
    "preferred": ["json_schema", "json_object", "prompt_json"],
    "required": "local_strict_validation",
    "fallbackMustBeExplicit": true
  },
  "responseSchema": "RardarExplosionExplanationV1",
  "timeoutClass": "standard",
  "cachePolicy": "explosion-artifact-revision-and-contract-version",
  "failurePolicy": "facts-publish-with-ai-unavailable"
}
```

AI must not alter `observedStarDelta`, insert a project, filter one out, break ties, reorder Top 5/Top 20, fabricate a missing 24-hour baseline or convert an external reported delta into Rardar's own observation.

## Cache contract

The cache key includes at least:

- strict routing group and scene;
- prompt/schema versions and response-schema digest;
- selected structured-output mode;
- requested and effective effort/temperature/output limit;
- complete source-revision set;
- capability-profile revision;
- normalized message digest.

Changing any item produces a new cache namespace. A result generated from an older repository push, static-analysis revision, observation artifact or prompt/schema version is not current. Invalid output and deterministic capability errors are never cached as successful business results.

## Failure contract

Stable implementation-level categories should distinguish:

- no strict `rardar` route;
- no model satisfies the profile;
- `model_capability_unverified` for unknown or stale required evidence;
- `model_capability_unsupported` for a proven unavailable requirement;
- `invocation_parameter_conflict` for incompatible scene and capability values;
- `structured_output_mode_unavailable` when no proven mode satisfies the ordered requirement;
- upstream deterministic rejection;
- transient provider/rate/timeout/circuit failure;
- invalid JSON/schema/evidence references;
- source revision changed before publication.

Capability errors are not provider outages. They must not degrade a healthy model, open the route circuit, enter cooldown, or trigger meaningless retry. The engine may try only another model in the strict `rardar` route whose proven capabilities satisfy the unchanged Invocation Profile; it never crosses to `default`.

## Publication boundary

The model returns a candidate only. Rardar validates strict JSON, Pydantic schema, evidence references, prompt/schema versions and source revisions before publishing an AI artifact atomically. The model never holds a generation lock during a network call and never modifies current generation data directly.

Fact collection, the Explosion Artifact, ranking and web availability continue when AI is unavailable. Project summary/profile may retain an older result only when its exact source revision still matches; otherwise the UI shows unavailable/stale rather than an invented substitute.
