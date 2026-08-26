# Rardar LLM Control Reuse

## Status and boundary

TopicEye is the only LLM control plane for Rardar. Rardar business code declares a scene, messages, and an optional reasoning effort; it never selects or receives a provider, API base, API key, or model ID.

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

Model support remains something to prove later with the user's chosen local model configuration and a bounded smoke test.

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

## Deferred local setup

This iteration leaves model configuration to the user. A later, independent `RARDAR-LLM-LOCAL-CONFIG-AND-SMOKE-01` may:

1. create or update a model in the local TopicEye model-management UI;
2. set its routing group to `rardar`;
3. choose provider, API base, API key, model and parameters;
4. perform a small, explicit smoke test against that chosen configuration.

That later task must not turn a smoke test into AI business implementation, deployment, or Production access.
