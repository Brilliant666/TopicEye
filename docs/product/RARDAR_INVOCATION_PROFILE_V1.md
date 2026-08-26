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

`"inherit"` asks the engine to consider the model-card default; it does not guarantee that the value will be sent. An explicit JSON `null` asks the engine to omit the parameter. In both cases the final request is governed by the selected model's `temperaturePolicy`. This distinction is necessary because loopback `0.3` is valid for the observed plain call but conflicts locally with `reasoning_effort = medium`; the current live model-row temperature itself remains unconfirmed.

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

The engine resolves three layers:

```text
model connection + defaults + hard capability bounds
  + Rardar Invocation Profile requirements
  -> validated effective invocation
```

Deterministic rules:

1. Connection fields always come from the TopicEye model row.
2. The Invocation Profile supplies the scene request; it never mutates the model-card default.
3. The engine selects `temperaturePolicy.whenReasoning` whenever `requestedReasoningEffort` is non-null, otherwise `temperaturePolicy.normal`.
4. `free` permits an allowed numeric scene value or a declared model default.
5. `default_only` permits only the profile's proven `defaultValue`; a different numeric or inherited value fails closed.
6. `omit` produces an effective request with no `temperature`, including when the model card has a default.
7. `unsupported` makes the model ineligible for that scene, and `unknown` fails closed or waits for an audited probe.
8. Effective output limit is `min(scene maxOutputTokens, proven model maxOutputTokens)`.
9. If the model limit is unknown and the scene requires a guaranteed bound, selection fails closed.
10. The requested effort must be explicitly supported for the configuration revision.
11. The chosen structured mode must be explicitly supported or be the profile's declared `prompt_json` fallback.
12. Timeout class is mapped centrally and remains under TopicEye's global hard cap.
13. All non-secret requested/effective values and capability-evidence revisions are logged.
14. An unsupported combination may select the next capable model in the same route; it never converts `0.3` to `1.0`, drops temperature outside an explicit `omit` policy, changes/downgrades effort, hard-codes behavior by model name, or falls back to `default`.

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
- capability unknown or stale;
- local request incompatibility;
- upstream deterministic rejection;
- transient provider/rate/timeout/circuit failure;
- invalid JSON/schema/evidence references;
- source revision changed before publication.

Capability mismatch must not degrade a healthy model or open the route circuit. Retry does not change a deterministic parameter conflict. The engine may fail over only to another model in the same route whose proven capabilities satisfy the unchanged Invocation Profile.

## Publication boundary

The model returns a candidate only. Rardar validates strict JSON, Pydantic schema, evidence references, prompt/schema versions and source revisions before publishing an AI artifact atomically. The model never holds a generation lock during a network call and never modifies current generation data directly.

Fact collection, the Explosion Artifact, ranking and web availability continue when AI is unavailable. Project summary/profile may retain an older result only when its exact source revision still matches; otherwise the UI shows unavailable/stale rather than an invented substitute.
