# Rardar Model Capability Profile V1

## Purpose

A Model Capability Profile describes what one existing TopicEye model configuration can accept end to end. It does not create a second model registry and does not replace TopicEye's provider, API base, encrypted key, model ID, route or call controls.

The profile is deliberately small. It covers only the three current Rardar scenes and the parameters needed to invoke them safely. Image, audio, realtime, tools, MCP, batch and broader multimodal capability matrices are outside V1.

## State model

Every capability has one of three states:

| State | Meaning | Invocation behavior |
| --- | --- | --- |
| `supported` | The complete configured route was explicitly declared and confirmed by an applicable audited probe. | May be selected when the requested value also satisfies constraints. |
| `unsupported` | An explicit configuration or audited probe proves the capability is rejected. | Must not be selected for a scene requiring it. |
| `unknown` | Evidence is absent, stale, library-only, conflicting or not end-to-end. | Never treated as supported; probe, choose another same-group model, or fail closed. |

`unknown` is a first-class result, not an error to hide. A successful plain-text request does not prove reasoning, structured output, token limits or usage detail.

## Evidence priority

Capability resolution uses this order:

1. **User explicit configuration** — an operator claim with an author and revision; it is not self-validating.
2. **Audited capability probe** — a versioned request/response observation for this exact model configuration and protocol mode.
3. **LiteLLM known-model information** — a useful local compatibility hint, never the only end-to-end authority for a self-hosted gateway.
4. **Unknown** — the safe default.

A later probe that contradicts an explicit claim does not get ignored. The resolved capability becomes `unsupported` or `unknown` with a conflict diagnostic until an operator resolves it. Model-name pattern matching alone cannot promote a new gateway model to `supported`.

Evidence becomes stale when the provider adapter, API base identity, upstream model ID, LiteLLM version, capability-profile version, or probe contract changes. Neither the API base value nor any credential is stored in probe evidence; non-secret configuration revisions are represented by hashes/IDs.

## V1 fields

The profile has exactly nine capability fields. `version` and evidence metadata are envelope fields, not additional capabilities.

| Field | Value when supported | Key constraint |
| --- | --- | --- |
| `protocolMode` | `chat_completions` or `responses` | Proves the full request path, not just an SDK feature. |
| `reasoningEfforts` | Subset of `medium`, `high`, `xhigh` | Each requested level must be proven; no silent downgrade. |
| `structuredOutputModes` | Subset of `json_object`, `json_schema`, `prompt_json` | Native support never replaces local strict validation. |
| `temperaturePolicy` | Conditional policy for normal and reasoning calls | A single boolean is invalid because the permitted value can change when reasoning is enabled. |
| `tokenParameterMode` | `max_tokens`, `max_completion_tokens`, or `max_output_tokens` | Records the effective upstream contract after transformation. |
| `maxContextTokens` | Positive integer | Unknown must not be replaced by a guessed catalog value. |
| `maxOutputTokens` | Positive integer | Engine clamps a scene request only against a proven limit. |
| `usageMode` | Supported token fields, for example `input_output` or `input_output_cache` | Missing fields remain unknown; values are not invented. |
| `reasoningUsageMode` | `included_in_output`, `separate`, or `not_reported` | Current TopicEye logs do not model reasoning-token detail separately. |

Each field value uses this shape:

```json
{
  "status": "unknown",
  "value": null,
  "source": "unknown",
  "evidenceRevision": null,
  "observedAt": null,
  "limitations": ["No end-to-end capability probe has confirmed this claim."]
}
```

Valid sources are `user_explicit`, `audited_probe`, `litellm_catalog`, and `unknown`. An implementation may retain multiple evidence records, but it must expose one deterministic resolved state and why.

`temperaturePolicy.value` has one small, provider-neutral rule shape:

```json
{
  "normal": "free",
  "whenReasoning": "default_only",
  "defaultValue": 1.0
}
```

Both mode fields use the same closed enum:

| Policy | Effective invocation behavior |
| --- | --- |
| `free` | A numeric scene value or the declared model default may be sent. |
| `default_only` | Only the model configuration's declared `defaultValue` may be sent; a different numeric value fails closed. |
| `omit` | The effective request must not contain `temperature`, even when the model card has a default. |
| `unsupported` | The model cannot serve a scene in that mode. |
| `unknown` | Selection fails closed until an applicable claim/probe resolves the policy. |

`defaultValue` is optional and must be a finite number when present. A `default_only` policy without a proven `defaultValue` is not usable. This structure is versioned with the surrounding profile, is independent of model/provider names, and deliberately avoids a general-purpose rules engine.

## Draft profile for the current route

The following is a research snapshot, not configuration to apply. It records the known distinction between local adapter behavior and unprobed upstream behavior.

```json
{
  "version": 1,
  "profileState": "draft",
  "configurationRevision": "research-2026-08-27",
  "capabilities": {
    "protocolMode": {
      "status": "supported",
      "value": "chat_completions",
      "source": "audited_probe",
      "evidenceRevision": "plain-smoke-and-loopback-v1",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": ["Responses API was not probed."]
    },
    "reasoningEfforts": {
      "status": "unknown",
      "value": ["medium", "high", "xhigh"],
      "source": "litellm_catalog",
      "evidenceRevision": "litellm-1.95.0-loopback",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": [
        "Medium passed the local adapter only when temperature was compatible.",
        "The configured upstream gateway was not reached by the blocked medium smoke.",
        "High and xhigh were not probed end to end."
      ]
    },
    "structuredOutputModes": {
      "status": "unknown",
      "value": ["json_object", "prompt_json"],
      "source": "litellm_catalog",
      "evidenceRevision": "litellm-1.95.0-loopback",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": [
        "json_object reached the loopback endpoint.",
        "Native gateway support and json_schema remain unverified.",
        "Local strict validation is required in every mode."
      ]
    },
    "temperaturePolicy": {
      "status": "unknown",
      "value": {
        "normal": "free",
        "whenReasoning": "default_only",
        "defaultValue": 1.0
      },
      "source": "audited_probe",
      "evidenceRevision": "litellm-1.95.0-temperature-control",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": [
        "The local adapter admitted 1.0 and rejected 0.3 when medium reasoning was requested.",
        "The configured upstream gateway was not reached by either rejected request.",
        "The 1.0 default-compatible value is loopback evidence, not confirmation of the current model row.",
        "CURRENT_LOCAL_MODEL_TEMPERATURE = UNCONFIRMED."
      ]
    },
    "tokenParameterMode": {
      "status": "supported",
      "value": "max_completion_tokens",
      "source": "audited_probe",
      "evidenceRevision": "litellm-1.95.0-loopback",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": ["TopicEye supplies max_tokens; LiteLLM transforms the upstream field."]
    },
    "maxContextTokens": {
      "status": "unknown",
      "value": null,
      "source": "litellm_catalog",
      "evidenceRevision": "litellm-1.95.0",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": ["The self-hosted gateway limit was not probed."]
    },
    "maxOutputTokens": {
      "status": "unknown",
      "value": null,
      "source": "litellm_catalog",
      "evidenceRevision": "litellm-1.95.0",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": ["The self-hosted gateway limit was not probed."]
    },
    "usageMode": {
      "status": "supported",
      "value": "input_output",
      "source": "audited_probe",
      "evidenceRevision": "existing-real-plain-smoke",
      "observedAt": "2026-08-27T00:00:00+08:00",
      "limitations": ["Cached-token fields are parsed when present but were not present in the smoke evidence."]
    },
    "reasoningUsageMode": {
      "status": "unknown",
      "value": null,
      "source": "unknown",
      "evidenceRevision": null,
      "observedAt": null,
      "limitations": ["No successful reasoning response was observed and TopicEye has no separate reasoning-token field."]
    }
  }
}
```

The fixed timestamp identifies this static example, not a fabricated probe time. A real profile must use the actual audited event time.

## Storage decision

`EXTRA_PARAMS_SUFFICIENT`

V1 can be stored in the existing `llm_models.extra_params.capabilities` namespace with no table and no migration:

```json
{
  "capabilities": {
    "version": 1,
    "profileState": "draft",
    "capabilities": {}
  },
  "litellm_params": {
    "timeout": 30
  }
}
```

The namespaces do not collide: `capabilities` is TopicEye policy data; `litellm_params` remains a narrow SDK-input namespace. Capability data must never contain an API key, Authorization value, raw headers, cookie, database URL, full prompt or response body.

### API and cache requirements before UI editing

The existing admin API can persist and return `extra_params`, and the model cache already loads it. That is sufficient storage but not yet a safe capability API:

- current create/update accepts an untyped dictionary;
- an update can replace the whole object and accidentally erase pricing, pool or LiteLLM settings;
- current model payloads return the whole `extra_params` object to an admin browser;
- `litellm_params.default_headers` and `extra_headers` may be secret-adjacent even though the primary API key is hidden;
- the current UI does not edit capability data;
- capability changes already have a usable invalidation boundary in the model cache, but no route selector consumes them yet.

The first implementation must therefore add a versioned validator, a sanitized capability projection, and a scoped merge/patch that changes only `extra_params.capabilities`. Validation must include the conditional temperature policy, reasoning-effort choices, structured-output modes, evidence source/revision, finite `defaultValue`, and fail-closed handling for unknown or stale evidence. It must not echo arbitrary header-bearing `litellm_params` through the capability endpoint. Existing model-list compatibility can remain admin-only, but the capability panel must consume only the safe projection. It requires no database migration and CI probes remain loopback/mock only.

## Invocation rules

Before a model configuration serves a Rardar Invocation Profile:

1. validate the profile envelope and version;
2. reject stale/conflicting evidence according to policy;
3. require `supported` for every mandatory requested capability;
4. choose `normal` or `whenReasoning`, then apply the exact temperature policy before model defaults are merged;
5. enforce proven context/output limits;
6. compute and log non-secret effective values;
7. keep capability errors deterministic and out of route health/failover counters;
8. never use `drop_params` to manufacture compatibility.

If no model in the strict `rardar` group satisfies the profile, return a stable capability-mismatch error. Do not fall back to TopicEye's `default` route and do not downgrade effort or output mode invisibly.

## Probe contract

A future capability probe is versioned and bounded. It records model-row ID, non-secret configuration revision, LiteLLM version, protocol mode, requested non-secret parameters, final URL path, final upstream model value, whether network was reached, status class, response content type, usage-field presence and a sanitized error category.

It never records credentials or Authorization, and it never persists full prompts or responses. CI uses loopback only. A real configured-route probe requires explicit operator authorization, short synthetic input, concurrency one and no business data.

## Minimal UI blueprint

The model card should eventually show:

- read-only derived LiteLLM request model;
- read-only upstream body model from the last applicable probe;
- profile version and state;
- protocol mode;
- effort and structured-output states;
- temperature compatibility and token parameter mode;
- proven limits;
- evidence source/revision/time and limitations;
- a bounded capability-test action with a sanitized result.

Unknown values must be visually distinct from unsupported ones. The panel edits capability claims, not keys or connection fields, and it does not enumerate a global model marketplace.
