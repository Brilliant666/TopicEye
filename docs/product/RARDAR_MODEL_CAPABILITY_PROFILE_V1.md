# Rardar Model Capability Profile V1

## Purpose

A Model Capability Profile describes what one existing TopicEye model configuration can accept end to end. It does not create a second model registry and does not replace TopicEye's provider, API base, encrypted key, model ID, route or call controls.

The profile is deliberately small. It covers only the three current Rardar scenes and the parameters needed to invoke them safely. Image, audio, realtime, tools, MCP, batch and broader multimodal capability matrices are outside V1.

## Normative contract

Everything from this heading through the invocation/storage rules is normative: future runtime code must validate and apply it. The later **Non-normative probe evidence** section is a research record only and must never be read as configuration.

### State model

Every capability has one of three states:

| State | Meaning | Invocation behavior |
| --- | --- | --- |
| `supported` | Applicable evidence establishes the complete configured route: either an accepted, versioned operator claim or an end-to-end audited probe, as required by policy. | May be selected when the requested value also satisfies constraints. |
| `unsupported` | An explicit configuration or audited probe proves the capability is rejected. | Must not be selected for a scene requiring it. |
| `unknown` | Evidence is absent, stale, library-only, conflicting or not end-to-end. | Never treated as supported; probe, choose another same-group model, or fail closed. |

`unknown` is a first-class result, not an error to hide. A successful plain-text request does not prove reasoning, structured output, token limits or usage detail.

### Evidence priority

Capability resolution uses this order:

1. **User explicit configuration** — an operator claim with an author and revision; it is not self-validating.
2. **Audited capability probe** — a versioned request/response observation for this exact model configuration and protocol mode.
3. **LiteLLM known-model information** — a useful local compatibility hint, never the only end-to-end authority for a self-hosted gateway.
4. **Unknown** — the safe default.

A later probe that contradicts an explicit claim does not get ignored. The resolved capability becomes `unsupported` or `unknown` with a conflict diagnostic until an operator resolves it. Model-name pattern matching alone cannot promote a new gateway model to `supported`.

Evidence becomes stale when the provider adapter, API base identity, upstream model ID, LiteLLM version, capability-profile version, or probe contract changes. Neither the API base value nor any credential is stored in probe evidence; non-secret configuration revisions are represented by hashes/IDs.

`source` identifies who supplied a claim; it does not prove that the claim is strong enough. `evidenceScope` distinguishes `operator_claim`, `loopback`, `real_provider`, `catalog`, and `none`. A loopback probe can prove TopicEye/LiteLLM request shaping, local parameter gates, and whether a request left the process. It cannot prove that the configured provider accepts a value or that the model executed a requested reasoning effort.

### V1 fields

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

Scalar/list capability fields use this evidence envelope:

```json
{
  "status": "unknown",
  "value": null,
  "source": "unknown",
  "evidenceScope": "none",
  "evidenceRevision": null,
  "verifiedAt": null,
  "probeVersion": null,
  "limitations": ["No end-to-end capability probe has confirmed this claim."]
}
```

Valid sources are `user_explicit`, `audited_probe`, `litellm_catalog`, and `unknown`. An implementation may retain multiple evidence records, but it must expose one deterministic resolved state, evidence scope, and explanation.

`temperaturePolicy` is the one composite capability. Its two branches use the same provider-neutral node shape:

```json
{
  "temperaturePolicy": {
    "normal": {
      "mode": "free",
      "fixedValue": null,
      "status": "supported",
      "source": "audited_probe",
      "evidenceScope": "real_provider",
      "evidenceRevision": "illustrative-normal-temperature-probe",
      "verifiedAt": "2026-01-01T00:00:00Z",
      "probeVersion": "temperature-probe-v1",
      "limitations": []
    },
    "whenReasoning": {
      "mode": "unknown",
      "fixedValue": null,
      "status": "unknown",
      "source": "unknown",
      "evidenceScope": "none",
      "evidenceRevision": null,
      "verifiedAt": null,
      "probeVersion": null,
      "limitations": ["No real-provider reasoning probe exists."]
    }
  }
}
```

This JSON is an illustrative valid shape, not evidence about the current route. Both branches use the same closed enum:

| Policy | Effective invocation behavior |
| --- | --- |
| `free` | A valid scene value may be sent; otherwise the model-card default may be sent, and no configured default means omission. |
| `omit` | The effective request must not contain `temperature`, even when the model card has a default. |
| `fixed` | The request must send the evidence-backed `fixedValue`; a conflicting scene value fails deterministically. |
| `unsupported` | The parameter is unavailable. A scene that depends on it fails; a scene that explicitly does not use it may omit it and record the limitation. |
| `unknown` | Any unattended invocation whose merge depends on this branch fails closed until applicable evidence resolves it. |

`fixedValue` is required, finite, and range-valid only when `mode = fixed`; its source must be `user_explicit` or `audited_probe`. For every other mode it must be absent or JSON `null`. `mode = fixed` with a catalog-only/unknown source is invalid. `mode = unknown` or `omit` with `fixedValue = 1.0` is invalid. This structure is versioned with the surrounding profile, independent of model/provider names, and deliberately avoids a general-purpose rules engine.

Examples of node shapes that are syntactically valid JSON but invalid under the normative schema:

```json
{
  "invalidTemperatureNodes": [
    {"mode": "unknown", "fixedValue": 1.0},
    {"mode": "omit", "fixedValue": 1.0},
    {"mode": "free", "fixedValue": 1.0},
    {"mode": "fixed", "fixedValue": null},
    {"mode": "fixed", "fixedValue": 1.0, "source": "litellm_catalog"}
  ]
}
```

A minimal valid fixed node is:

```json
{
  "mode": "fixed",
  "fixedValue": 0.2,
  "status": "supported",
  "source": "audited_probe",
  "evidenceScope": "real_provider",
  "evidenceRevision": "example-fixed-temperature-probe",
  "verifiedAt": "2026-01-01T00:00:00Z",
  "probeVersion": "temperature-probe-v1",
  "limitations": []
}
```

### Draft normative profile for the current route

The following is the conservative profile that current evidence permits. It contains no loopback-derived fixed value. It is a draft contract, not configuration applied by this PR.

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
      "evidenceScope": "real_provider",
      "evidenceRevision": "existing-real-plain-smoke",
      "verifiedAt": null,
      "probeVersion": "plain-smoke-v1",
      "limitations": ["The exact event time was not retained; Responses API was not probed."]
    },
    "reasoningEfforts": {
      "status": "unknown",
      "value": null,
      "source": "audited_probe",
      "evidenceScope": "loopback",
      "evidenceRevision": "litellm-1.95.0-loopback",
      "verifiedAt": null,
      "probeVersion": "rardar-loopback-v1",
      "limitations": [
        "Medium passed the local adapter only when temperature was compatible.",
        "The configured upstream gateway was not reached by the blocked medium smoke.",
        "High and xhigh were not probed end to end."
      ]
    },
    "structuredOutputModes": {
      "status": "unknown",
      "value": null,
      "source": "audited_probe",
      "evidenceScope": "loopback",
      "evidenceRevision": "litellm-1.95.0-loopback",
      "verifiedAt": null,
      "probeVersion": "rardar-loopback-v1",
      "limitations": [
        "json_object reached the loopback endpoint.",
        "Native gateway support and json_schema remain unverified.",
        "Local strict validation is required in every mode."
      ]
    },
    "temperaturePolicy": {
      "normal": {
        "mode": "unknown",
        "fixedValue": null,
        "status": "unknown",
        "source": "audited_probe",
        "evidenceScope": "loopback",
        "evidenceRevision": "litellm-1.95.0-temperature-control",
        "verifiedAt": null,
        "probeVersion": "rardar-loopback-v1",
        "limitations": [
          "A real plain call succeeded, but its effective temperature was not recorded.",
          "Loopback 0.3 reached the local endpoint but does not establish real-provider support."
        ]
      },
      "whenReasoning": {
        "mode": "unknown",
        "fixedValue": null,
        "status": "unknown",
        "source": "audited_probe",
        "evidenceScope": "loopback",
        "evidenceRevision": "litellm-1.95.0-temperature-control",
        "verifiedAt": null,
        "probeVersion": "rardar-loopback-v1",
        "limitations": [
          "Loopback 0.3 was rejected before network and 1.0 reached loopback only.",
          "No real-provider reasoning temperature policy has been verified.",
          "CURRENT_LOCAL_MODEL_TEMPERATURE = UNCONFIRMED."
        ]
      }
    },
    "tokenParameterMode": {
      "status": "unknown",
      "value": null,
      "source": "audited_probe",
      "evidenceScope": "loopback",
      "evidenceRevision": "litellm-1.95.0-loopback",
      "verifiedAt": null,
      "probeVersion": "rardar-loopback-v1",
      "limitations": ["TopicEye supplies max_tokens; LiteLLM transforms the upstream field."]
    },
    "maxContextTokens": {
      "status": "unknown",
      "value": null,
      "source": "litellm_catalog",
      "evidenceScope": "catalog",
      "evidenceRevision": "litellm-1.95.0",
      "verifiedAt": null,
      "probeVersion": null,
      "limitations": ["The self-hosted gateway limit was not probed."]
    },
    "maxOutputTokens": {
      "status": "unknown",
      "value": null,
      "source": "litellm_catalog",
      "evidenceScope": "catalog",
      "evidenceRevision": "litellm-1.95.0",
      "verifiedAt": null,
      "probeVersion": null,
      "limitations": ["The self-hosted gateway limit was not probed."]
    },
    "usageMode": {
      "status": "supported",
      "value": "input_output",
      "source": "audited_probe",
      "evidenceScope": "real_provider",
      "evidenceRevision": "existing-real-plain-smoke",
      "verifiedAt": null,
      "probeVersion": "plain-smoke-v1",
      "limitations": ["Cached-token fields are parsed when present but were not present in the smoke evidence."]
    },
    "reasoningUsageMode": {
      "status": "unknown",
      "value": null,
      "source": "unknown",
      "evidenceScope": "none",
      "evidenceRevision": null,
      "verifiedAt": null,
      "probeVersion": null,
      "limitations": ["No successful reasoning response was observed and TopicEye has no separate reasoning-token field."]
    }
  }
}
```

Because both temperature branches are `unknown`, current unattended Rardar calls that require temperature-policy resolution must fail with `model_capability_unverified`. Neither the plain success nor loopback evidence is promoted to `free`, `omit`, or `fixed` without an applicable real-provider probe or explicit operator claim.

## Non-normative probe evidence

This repository research record explains the diagnosis. It is not a Capability Profile, is not stored under `extra_params.capabilities`, and must never supply runtime parameters:

```json
{
  "recordType": "non_normative_probe_evidence",
  "litellmVersion": "1.95.0",
  "temperature03": "rejected_before_network",
  "temperature10": "request_reached_loopback",
  "realProviderCapabilityVerified": false,
  "currentModelTemperature": "unconfirmed",
  "modelIdRootCause": false,
  "responseFormatRootCause": false
}
```

The `1.0` observation proves only that this LiteLLM version emitted a loopback request under that synthetic input. It is not a provider default, model default, required value, or proof that reasoning was executed. Future implementation code must not read this research record.

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

The first implementation must therefore add a versioned validator, a sanitized capability projection, and a scoped merge/patch that changes only `extra_params.capabilities`. Validation must include the conditional temperature policy, reasoning-effort choices, structured-output modes, source plus evidence scope/revision, the `fixedValue` invariants, and fail-closed handling for unknown or stale evidence. It must not echo arbitrary header-bearing `litellm_params` through the capability endpoint. Existing model-list compatibility can remain admin-only, but the capability panel must consume only the safe projection. It requires no database migration and CI probes remain loopback/mock only.

## Invocation rules

Before a model configuration serves a Rardar Invocation Profile:

1. validate the profile envelope and version;
2. reject stale/conflicting evidence according to policy;
3. require `supported` for every mandatory requested capability;
4. choose `normal` or `whenReasoning`, then apply `free`, `omit`, `fixed`, `unsupported`, or `unknown` before model defaults are merged;
5. enforce proven context/output limits;
6. compute and log non-secret effective values;
7. keep capability errors deterministic and out of route health/failover counters;
8. never use `drop_params` to manufacture compatibility.

Stable errors distinguish `model_capability_unverified`, `model_capability_unsupported`, `invocation_parameter_conflict`, and `structured_output_mode_unavailable`. They are deterministic capability results, not provider health failures: do not retry them, open a circuit, enter cooldown, or fall back to TopicEye's `default` route. A later implementation may try another proven-capable model only inside the strict `rardar` group.

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
