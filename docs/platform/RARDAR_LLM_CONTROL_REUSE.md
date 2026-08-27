# Rardar LLM Control Reuse

## Status and boundary

TopicEye is the only LLM control plane for Rardar. Rardar business code declares a scene, messages, and an optional reasoning effort; it never selects or receives a provider, API base, API key, or model ID.

The shared control boundary is implemented and locally configured, but the Rardar AI runtime is **not complete**. The current model-capability and scene-invocation contracts are documented in [Rardar AI Engine Adaptation](RARDAR_AI_ENGINE_ADAPTATION.md), [Model Capability Profile V1](../product/RARDAR_MODEL_CAPABILITY_PROFILE_V1.md), and [Rardar Invocation Profile V1](../product/RARDAR_INVOCATION_PROFILE_V1.md). No Rardar business prompt or AI artifact publication is enabled by those docs.

The formal call path is:

```text
Rardar feature
  -> app.services.rardar_llm_control
  -> TopicEye LLM provider facade
  -> TopicEye route / retry / failover / rate limit / circuit / cache / logging
  -> model selected from TopicEye llm_models configuration
```

This boundary adds no provider, HTTP client, model table, prompt table, queue, Worker, or environment variable. It does not configure or call a real model and it does not make any current Rardar page depend on AI.

## Configuration ownership

TopicEye's existing model-management API and UI remain authoritative for:

- provider and compatible API base;
- encrypted API key;
- model ID and provider-specific parameters;
- enabled state, routing priority and cooldown;
- temperature, maximum output tokens and request rate;
- token pricing and cost accounting.

Users can configure any provider, compatible API base, key, available model, priority, and other model parameters already supported by TopicEye. Rardar code does not change when those choices change. API keys continue to be encrypted at rest and model-list responses expose only `api_key_set`, never the key.

There are deliberately no `RARDAR_LLM_*` settings and no hard-coded endpoint, provider, model, or credential.

## Strict `rardar` route

`routing_group = rardar` is a logical workload route, not a provider alias. The shared model cache supports a strict lookup mode used by the Rardar boundary. If no enabled model belongs to this group, the boundary returns `rardar_llm_not_configured`.

It never falls back to `default`, a TopicEye content model, or an arbitrary enabled model. Ordering, same-group failover, retries, cooldown, concurrency, rate limits, and the route circuit breaker remain implemented by TopicEye. A future fallback must be an explicit TopicEye routing configuration rather than business-code guessing.

The first scene contract is intentionally small:

- `rardar_project_summary`;
- `rardar_project_profile`;
- `rardar_explosion_explanation`.

No prompt or business feature is implemented for these scenes in this iteration.

## Reasoning effort

The shared provider call accepts `None`, `medium`, `high`, or `xhigh`:

- `None` omits the parameter and leaves provider/model defaults in control;
- the other values are passed unchanged to the bottom LiteLLM call;
- an invalid value fails before any provider call;
- an unsupported effort is never silently downgraded;
- effort participates in cache identity, returned metadata, and safe operational logs.

The configured local route has proven plain-text connectivity. Its first structured `medium` smoke remains blocked: non-normative loopback evidence shows that LiteLLM `1.95.0` recognizes `gpt-5.6-sol`, rejects explicit `temperature = 0.3` plus medium before network, and emits a loopback request with synthetic `temperature = 1.0`. `MODEL_ID_NOT_ROOT_CAUSE` and `LOCAL_BEFORE_NETWORK` are confirmed; removing `response_format` does not change the rejection. The earlier real smoke did not expose its effective temperature and this iteration did not obtain an authenticated model-row read, so `CURRENT_LOCAL_MODEL_TEMPERATURE = UNCONFIRMED`. Neither loopback value establishes a real-provider default or capability, and the normative `temperaturePolicy.whenReasoning` therefore remains `unknown` and fail-closed. The engine must not rewrite a value to `1.0`, silently omit temperature, or downgrade effort.

## Structured results

`call_rardar_structured` reuses TopicEye's existing JSON request mode and response-format fallback, then applies a strict local boundary:

1. strict UTF-8 text handling;
2. strict JSON decoding;
3. rejection of duplicate object keys;
4. rejection of `NaN` and infinities;
5. caller-supplied Pydantic validation in strict mode;
6. enforcement of top-level type, required fields, field types, and the caller model's extra-field policy.

The cache identity includes route, scene, message digest (owned by the existing cache), reasoning effort, prompt version, schema version, response-schema digest, and response format. Different efforts or contract versions cannot share a cached response. Invalid output is never returned as a business object.

## Stable errors and metadata

The public error contract is limited to:

| Code | Meaning |
| --- | --- |
| `rardar_llm_not_configured` | No enabled model is configured for the strict `rardar` route. |
| `rardar_llm_unavailable` | The configured control path is temporarily unavailable, exhausted, timed out, or circuit-open. |
| `rardar_llm_invalid_output` | Output is not strict JSON or fails the caller's schema. |
| `rardar_llm_request_rejected` | The local request or an upstream deterministic request is invalid/rejected. |

Future capability-aware selection additionally distinguishes `model_capability_unverified`, `model_capability_unsupported`, `invocation_parameter_conflict`, and `structured_output_mode_unavailable`. These deterministic results do not open circuits, enter cooldown, trigger meaningless retry, or permit fallback to TopicEye's `default` route.

Rardar errors do not expose prompts, raw provider responses, endpoints, model configuration, stack traces, or credentials. Shared call-failure logs and the model-test endpoint now persist/return only a bounded operational category instead of the raw provider exception.

Successful results may report scene, route, non-secret model display/internal ID, provider category, reasoning effort, prompt/schema versions, latency, cache state, and usage when the current shared layer provides it. Missing metadata remains `None`; it is never invented. API base and API key are never result metadata.

## Fact isolation

The audited Explosion Artifact, Intelligence Adapter, and Today UI remain a separate fact-only chain. Missing model configuration, provider failure, or an open LLM circuit does not affect fact loading, ranking, or HTTP availability. This iteration changes no Explosion DTO, rank, artifact, Rardar repository file, or business database fact.

## Security and rollback

- Mock keys are the only credentials used by tests; no real provider is contacted.
- Decrypted keys exist only at the existing bottom provider call boundary.
- Ordinary error responses and persisted failure messages do not copy upstream exception bodies.
- The implementation uses existing `llm_models` and `llm_call_logs`; there is no schema migration.

Rollback is an application-code revert. No database downgrade or data conversion is required. Existing TopicEye callers retain their historical permissive route behavior; only the explicit Rardar boundary requests strict routing.

## Current adaptation boundary

The user has configured one enabled `rardar` model and completed a bounded plain/structured smoke. That configuration remains owned by TopicEye and was not modified during the contract audit.

The next implementation, after human review, is a versioned and secret-safe Model Capability Profile inside the existing model control plane. Its normal/reasoning `free/omit/fixed/unsupported/unknown` temperature policy, `fixedValue` invariants, effort and structured-output capabilities, source plus evidence scope, safe projection, scoped patch and unknown-fail-closed behavior must precede scene parameter merging, a real reasoning compatibility probe, and Rardar-owned prompt implementation. Probe evidence is not configuration. Until those slices are complete, documentation and UI must not describe the Rardar AI runtime as finished.
