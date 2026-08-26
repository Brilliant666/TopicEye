# Rardar AI Engine Adaptation Contract

## Status and scope

This document closes the research contract for adapting Rardar scenes to TopicEye's existing AI engine. It is a design record, not an implementation. TopicEye remains the only model control plane; no second provider abstraction, key store, model table, or direct Rardar HTTP client is proposed.

Evidence was collected against TopicEye main `1ecb44a0154650dadd5525d7ad12f95a80b58559`, LiteLLM `1.95.0`, the existing successful plain-text smoke, and an isolated loopback server. No real key was read, no model setting was changed, and no additional provider request was made.

The two companion contracts are:

- [Model Capability Profile V1](../product/RARDAR_MODEL_CAPABILITY_PROFILE_V1.md)
- [Rardar Invocation Profile V1](../product/RARDAR_INVOCATION_PROFILE_V1.md)

## One control plane

The intended call path is:

```text
Rardar scene
  -> Rardar Invocation Profile
  -> app.services.rardar_llm_control
  -> TopicEye route / retry / failover / admission / circuit / cache / logging
  -> TopicEye llm_models row + Model Capability Profile
  -> LiteLLM SDK and provider transformation
  -> configured upstream API
```

| Concern | Owner | Notes |
| --- | --- | --- |
| Model CRUD and operator UI | TopicEye | Existing `llm_models` API and admin UI remain authoritative. |
| Provider, API base, model ID | TopicEye | Connection configuration; never copied into an Invocation Profile. |
| API-key encryption | TopicEye | Decryption remains at the bottom call boundary. |
| Route priority and strict `rardar` group | TopicEye | Rardar must not borrow `default`. |
| Retry, failover and cooldown | TopicEye | Existing implementation; capability mismatch is deterministic, not a health failure. |
| Rate/concurrency limits and circuit breaker | TopicEye | Existing implementation and metrics. |
| Response cache, call logs, token/cost accounting | TopicEye | Cache identity already includes Rardar scene/effort/schema identity. |
| Business prompt, evidence and output schema | Rardar | Defined by a versioned Invocation Profile. |
| SDK call, provider prefix, request transformation | LiteLLM | An internal TopicEye dependency, not a product control plane. |

LiteLLM's own documentation describes provider-prefixed SDK model names such as `openai/gpt-5`, unified OpenAI-shaped responses, and separate Chat Completions and Responses entry points. Those are library capabilities, not proof that a particular self-hosted gateway implements every option. See the [LiteLLM SDK documentation](https://docs.litellm.ai/) and the [official LiteLLM architecture](https://github.com/BerriAI/litellm/blob/litellm_internal_staging/ARCHITECTURE.md).

OpenAI's current [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) recommends the Responses API for reasoning workflows while retaining Chat Completions support. That guidance is not sufficient to switch TopicEye's protocol: the configured self-hosted gateway and each required parameter still need an audited capability probe.

## Model configuration semantics

The current configuration has `provider = openai`, `model_id = gpt-5.6-sol`, a configured OpenAI-compatible API base, and `routing_group = rardar`.

| Field | Actual meaning in current code | Current-path result |
| --- | --- | --- |
| `provider` | Default LiteLLM protocol/transform provider when no explicit override exists. It is not the upstream vendor or hostname. | `openai` selects the OpenAI-compatible transformation. |
| `model_id` | Operator-facing upstream model identifier unless it is already a provider-prefixed LiteLLM model string. | `gpt-5.6-sol`. |
| `api_base` | Connection endpoint passed to LiteLLM. It does not select model capabilities. | Configured; value deliberately not copied into this record. |
| `extra_params` | Existing JSON extension namespace for pricing, pool and selected LiteLLM controls. | No capability contract exists yet. |
| `extra_params.litellm_provider` | Optional override used when deriving a prefixed request model. | Overrides `provider` for derivation. |
| `extra_params.litellm_model` | Highest-precedence explicit LiteLLM request model. | Can bypass automatic derivation. |
| `extra_params.litellm_params.model` | Alternate explicit request-model location with the same resolver precedence. | Can bypass automatic derivation. |
| `request_model` | Internal string passed from TopicEye to LiteLLM. | `openai/gpt-5.6-sol`. |
| Upstream JSON `model` | Provider prefix removed by LiteLLM's OpenAI transformation. | `gpt-5.6-sol`. |

Resolution order in [`model_resolver.py`](../../backend/app/services/llm/model_resolver.py) is:

1. explicit `extra_params.litellm_model` or `extra_params.litellm_params.model`;
2. an already-prefixed `model_id`;
3. `litellm_provider`, `custom_llm_provider`, or `provider` plus the bare `model_id`;
4. the bare model ID if no provider is available.

The API base is never inspected to guess a provider. That separation is correct and should remain.

## Loopback protocol evidence

The probe used the installed LiteLLM `1.95.0`, TopicEye's real resolver, candidate builder, provider facade, call engine, and Rardar route semantics. Only model lookup and usage-log persistence were replaced with in-memory doubles. The HTTP target was a random loopback port implementing `POST /v1/chat/completions`; the key was a non-secret test token and was neither recorded nor printed.

The A-D matrix used `temperature = 1.0` to isolate model-name behavior from sampling compatibility:

| Case | Operator configuration | Internal `request_model` | Upstream body `model` | Plain | `medium` | `medium` + `json_object` |
| --- | --- | --- | --- | --- | --- | --- |
| A | `openai` + `gpt-5.6-sol` | `openai/gpt-5.6-sol` | `gpt-5.6-sol` | reached, 1 request | reached, 1 request | reached, 1 request |
| B | `openai` + `openai/gpt-5.6-sol` | `openai/gpt-5.6-sol` | `gpt-5.6-sol` | reached, 1 request | reached, 1 request | reached, 1 request |
| C | A plus explicit `litellm_model = openai/gpt-5.6-sol` | `openai/gpt-5.6-sol` | `gpt-5.6-sol` | reached, 1 request | reached, 1 request | reached, 1 request |
| D | `openai` + unregistered fake name | `openai/rardar-unregistered-loopback-model` | fake name | reached, 1 request | local rejection, 0 requests | local rejection, 0 requests |

For A-C, LiteLLM also converted TopicEye's `max_tokens = 256` to upstream `max_completion_tokens = 256`. All calls targeted `/v1/chat/completions`.

A focused control then used the TopicEye model-card default `temperature = 0.3` with case A:

| Call | Result | Network requests | Diagnostic |
| --- | --- | --- | --- |
| Plain, no effort | success | 1 | Upstream body retained `temperature = 0.3`. |
| `reasoning_effort = medium` | `UnsupportedParamsError` | 0 | LiteLLM rejected the temperature/effort combination locally. |
| `medium` + `json_object` | `UnsupportedParamsError` | 0 | Same local temperature diagnostic. |

The diagnostic states that the GPT-5 transformation does not accept `temperature = 0.3` with that reasoning mode. This reproduces the existing smoke pattern: plain succeeds; the structured request fails; removing `response_format` still fails because the retry preserves both `reasoning_effort` and the inherited temperature. The earlier real smoke did not record its non-secret effective temperature, and no authenticated model-row read was available in this iteration. Therefore `CURRENT_LOCAL_MODEL_TEMPERATURE = UNCONFIRMED`: the exact `0.3` match is a high-confidence inference from code and identical loopback behavior, not a confirmed runtime fact. The first implementation must expose sanitized effective parameters so a later authorized probe can confirm them directly.

### Root-cause decision

`MODEL_ID_NOT_ROOT_CAUSE`

- Bare, prefixed and explicit representations resolve to the same internal and upstream model values.
- With compatible sampling input, all three forms forward `reasoning_effort = medium` and `response_format` to the loopback endpoint.
- An actually unregistered model is rejected locally for effort, which proves the model registry can cause this class of failure, but the configured `gpt-5.6-sol` is registered in the installed map.
- The high-confidence reproduced blocker is the parameter merge: the Rardar boundary combines reasoning effort with a non-default temperature; loopback `0.3` reproduces the observed local failure exactly.
- `response_format` is not the cause because a reasoning-only call reproduces the same local error.
- No request reached the real upstream in the blocked smoke, so real gateway support for `medium` and native structured output remains unverified until a later capability probe.

Confirmed facts are the derived `openai/gpt-5.6-sol` request model, upstream body `model = gpt-5.6-sol`, successful plain path, local-before-network reasoning rejection, and the same failure without `response_format`. The actual model-row temperature is not confirmed. Confidence is high for the local failure location and parameter interaction, and deliberately unknown for the unprobed upstream capability.

Reasoning-failure classification:

- location: `LOCAL_BEFORE_NETWORK` for the reproduced `temperature = 0.3` + `medium` request;
- model registry: involved, because it selects the GPT-5 parameter rules and rejects the fake model, but it correctly recognizes `gpt-5.6-sol`;
- provider mapping: involved in selecting the OpenAI-compatible transformation, with no evidence of a wrong mapping;
- Model ID: not the root cause;
- `response_format`: not the root cause;
- upstream: not reached by the reproduced blocked call, so upstream reasoning support remains unknown.

## Parameter ownership and current behavior

| Parameter | Current TopicEye behavior | Owner today | Capability risk |
| --- | --- | --- | --- |
| `model` | Always sent to LiteLLM as a prefixed request model; transformed before upstream HTTP. | Model configuration + resolver | Prefix and upstream value are different concepts. |
| `messages` | Always sent. | Business caller | Repository evidence must be treated as untrusted data. |
| `api_base` | Sent only when configured. | Model configuration | Protocol shape cannot be inferred from URL alone. |
| `api_key` | Sent only when configured; decrypted at the bottom boundary. | Model configuration | Must never enter profile, cache identity, response or ordinary logs. |
| `temperature` | Always receives either a caller value or model-card default. Rardar currently passes `None`, so the card default wins. | Model card today | Support can be conditional on effort. |
| `max_tokens` | Always receives caller or card value. | Model card today | LiteLLM converted it to `max_completion_tokens` for the current model. |
| `response_format` | Sent only for structured calls; current Rardar value is `json_object`. | Rardar call boundary | Native support is not yet proven upstream. |
| `reasoning_effort` | Sent only when requested; `medium`, `high`, `xhigh` are accepted by the TopicEye boundary. | Rardar scene | Must not be dropped or downgraded silently. |
| `timeout` | Always bounded by TopicEye's global hard cap; model `litellm_params.timeout` can only reduce it. | TopicEye engine + model config | Deep calls may need an explicit future timeout class. |
| `num_retries` | Defaults to zero at LiteLLM because TopicEye owns retry/failover; allowlisted config can override. | TopicEye engine | Avoid multiplicative retries. |
| `extra_body` | Not allowlisted or sent by the current engine. | None | Must not be assumed available. |
| Other `litellm_params` | Only a narrow allowlist is copied: API version, provider, headers/query, metadata, retries, organization, timeout and drop policy. | Model config | Header-bearing fields are secret-adjacent and must not leak through a capability API. |
| Tool calling | Not used by current Rardar scenes. | Deferred | No capability claim. |
| Usage | Input/output/cache tokens and actual model are extracted into TopicEye call logs when present. | TopicEye engine | Reasoning-token detail is not currently modeled; Rardar result metadata does not currently receive usage. |

The original defaults and presets target `gpt-4.1-mini`, ordinary Chat Completions, topic analysis, summaries and creator workflows. A globally useful `temperature = 0.3` is therefore not a safe reasoning default. Model connection defaults and Rardar scene requirements must be separate.

## TopicEye UI semantic audit

| Current UI | Actual meaning | Risk | Recommended label/help |
| --- | --- | --- | --- |
| Provider | LiteLLM protocol transformation default | Can be mistaken for the upstream vendor or billing provider. | **Protocol adapter / call type**. Explain that `openai` also covers a compatible custom API base. |
| Model ID | Usually upstream body model, but may also accept a prefixed LiteLLM route | Users may think only official catalog IDs work or that it equals the internal request model. | **Upstream model ID**. Recommend a bare gateway model ID; reserve an advanced override for exceptional routing. |
| OpenAI example `gpt-4.1-mini` | One example, not an allowlist | Reinforces official-catalog assumptions and old sampling defaults. | Add a custom-base example and say availability is proven by capability probe. |
| API Base help | Connection base for the selected protocol | `/v1` guidance can be read as universal and may create doubled paths. | Explain that path joining is protocol-specific and testable; do not infer capabilities from it. |
| Actual Request Model | Already shown only when different | Easy to miss and not explained. | Always show a read-only **Derived request model**, plus a second read-only **Upstream body model** after probe. |
| Routing Group | Workload route | Users may interpret `rardar` as provider/model. | Describe it as a strict workload pool; no fallback to `default`. |
| Temperature / Max Tokens | Card defaults | Presented as universally safe. | Mark as defaults, show capability conflicts, and display the scene's effective values in tests. |

The smallest future UI addition is one versioned capability panel with supported/unsupported/unknown states, protocol mode, reasoning-effort choices, structured-output modes, token mode, limits, evidence source and last probe revision. A capability test must show the exact non-secret effective request contract; it must not become a model marketplace.

## Prompt and preset disposition

Technical callability does not imply product-semantic reuse.

| Asset | Disposition | Reason |
| --- | --- | --- |
| Classification prompt | `RARDAR_ADAPTABLE` | Its dual-axis mechanism is reusable, but the TopicEye taxonomy and output contract are content-oriented. Rardar needs repository capabilities and evidence. |
| Analysis prompt, including paper analysis | `REJECT_FOR_RARDAR` | Curation, creator value, viral potential and old weighted scores conflict with Rardar facts and reuse decisions. |
| Prescreen prompt | `RARDAR_ADAPTABLE` | Escalation scaffolding can inspire a gate, but its high-value/creator semantics cannot be copied. |
| Creation prompts and platform templates | `TOPICEYE_ONLY` | Xiaohongshu, video and article production plans are TopicEye product behavior. |
| Daily report and digest prompts | `TOPICEYE_ONLY` | They rank content for creators and use TopicEye source/category fields. |
| Enrichment prompt | `REJECT_FOR_RARDAR` | Creator angles and storytelling hooks are not repository capability evidence. |
| Angle recommendation prompt | `TOPICEYE_ONLY` | Explicit creator/viral-angle task. |
| Route, strict JSON parser, prompt-safety utilities, cache, logs and usage | `GENERIC_REUSABLE` | Infrastructure, not a business prompt. |

Rardar owns new, versioned prompt contracts only for `rardar_project_summary`, `rardar_project_profile`, and `rardar_explosion_explanation`. Find Project remains deferred. No existing TopicEye business prompt is copied into those scenes.

## Parameter merge contract

The future engine computes an effective invocation from three layers:

1. **Model configuration** supplies connection defaults, hard limits and the Capability Profile.
2. **Invocation Profile** supplies scene intent and an explicit value, `omit`, or `inherit` policy.
3. **AI engine** validates compatibility, computes effective values, chooses only a capable model in the same route, and records the result.

Rules:

- the engine selects `temperaturePolicy.whenReasoning` for a scene requesting effort and `temperaturePolicy.normal` otherwise;
- `free` permits a scene value or the declared model default;
- `default_only` permits only the capability profile's proven default value;
- `omit` removes temperature from the effective request even when the model card has a default;
- `unsupported` makes the model ineligible and `unknown` fails closed pending evidence;
- a numeric scene value wins over a model default only when the selected policy allows it;
- `temperature = "inherit"` considers the model default subject to policy; explicit `null` requests omission;
- effective maximum output is the lesser of the scene request and proven model limit;
- unknown limits fail closed when a hard guarantee is required;
- unsupported effort returns a stable capability error or selects another capable model in the same `rardar` group;
- effort is never silently changed;
- the engine never changes `0.3` to `1.0`, drops effort, or selects a rule by model-name pattern;
- native structured-output fallback is allowed only when the Invocation Profile names the fallback and the selected mode is recorded;
- provider/base/key/model never appear in an Invocation Profile.

This contract fixes the over-strict earlier boundary where Rardar could not express any temperature or output requirement while still preventing business code from owning connection configuration.

## Structured-output modes

| Mode | Capability requirement | Typical failure | Local verification | Unattended suitability |
| --- | --- | --- | --- | --- |
| Native `json_object` | Gateway and model accept JSON mode | Local parameter gate or upstream 4xx; JSON shape is unconstrained | Still mandatory | Acceptable only after probe and with strict schema validation. |
| Native `json_schema` | Gateway/model support the exact schema dialect | Unsupported keyword/mode or partial enforcement | Still mandatory | Preferred when proven, never assumed from model name. |
| Prompt JSON + local strict validation | Reliable text completion | Fenced prose, malformed JSON or schema drift | Primary safety boundary | Acceptable as an explicit bounded fallback, not an invisible retry. |

Every mode must reject duplicate keys, `NaN`/infinity, wrong top-level type, wrong field type, missing required fields and forbidden extras according to the Pydantic contract. Prompt and schema versions must be part of cache identity and result provenance.

## Security boundary

README text, source code, comments, issues and release notes are untrusted evidence. They are data, never instructions. Rardar scene prompts must separate trusted system policy from delimited evidence and explicitly forbid following repository requests to reveal secrets, call tools, execute commands, access the network, change ranking rules or write databases.

The first version has no model tools, no repository-code execution, no direct database writes, and no ability to alter the Explosion Board's factual order. Parsed output is published only after local strict validation and source-version checks.

## Implementation roadmap

No slice starts from this document automatically.

1. **RARDAR-MODEL-CAPABILITY-PROFILE-01** — add versioned `extra_params.capabilities` validation; the normal/reasoning conditional temperature policy; reasoning-effort and structured-output modes; evidence source/revision; a secret-safe read projection; and a scoped merge/patch. It requires no database migration, uses loopback/mock tests only, and treats unknown as fail closed.
2. **RARDAR-INVOCATION-PROFILES-01** — add the three versioned scene profiles, final effective-parameter calculation, temperature-policy application, reasoning-effort requirements, output budgets, prompt/schema versions, stable mismatch errors and effective-parameter audit metadata. No business prompt execution.
3. **RARDAR-REASONING-COMPATIBILITY-01** — only after slices 1-2 exist, use explicit operator authorization to probe the configured route for medium/high/xhigh and structured modes, then resolve compatibility through capability evidence and merge rules. Do not add a LiteLLM model-name special case, `drop_params`, or effort downgrade.
4. **RARDAR-PROMPT-CONTRACTS-01** — implement only the three Rardar-owned prompts and strict response schemas after slices 1-3 are reviewed.

The first implementation PR is slice 1. Expected areas are the existing model API/schema service, resolver-facing projection, admin model semantics, focused tests and these documents. It requires no new table or migration, does not change provider execution, uses loopback/mock probes only, and passes when all capability state—including conditional temperature policy—is versioned, secret-safe, independently patchable, evidence-backed, invalidated with the existing model cache, and fail-closed when unknown.
