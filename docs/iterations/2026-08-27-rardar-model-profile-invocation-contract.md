# 2026-08-27 — Rardar Model Profile and Invocation Contract

## Goal and baseline

This docs-only research iteration defines how Rardar uses TopicEye's existing AI engine without creating a second control plane. The linked worktree and branch started clean from TopicEye main `1ecb44a0154650dadd5525d7ad12f95a80b58559`. An independent timezone-only Hotfix PR #7 later merged as `b26a64656b3b097e0445f6f590009ec32589435f`; this branch was rebased onto that exact main without changing the research scope.

The existing local runtime worktree remained read-only and unchanged. Its configured strict `rardar` route has provider `openai`, model ID `gpt-5.6-sol`, a configured OpenAI-compatible API base and an enabled/available model. No credential, encrypted value, administrator password or full Authorization header was read or recorded.

Existing real evidence before this iteration was:

- plain call successful through `routing_group = rardar`, with no default fallback, model `gpt-5.6-sol`, 5,531 ms and 68/32/100 input/output/total tokens;
- structured `medium` call rejected with `UnsupportedParamsError`;
- the first attempt had `response_format` and effort, and the existing fallback without `response_format` was rejected again;
- failed calls reported zero usage, so the evidence did not prove an upstream rejection.

## Audit result

TopicEye remains authoritative for model CRUD, encrypted keys, protocol provider, API base, model ID, routing, retry/failover, rate/concurrency limits, circuit breaker, cache, call logs and token/cost accounting. LiteLLM `1.95.0` is the internal SDK/translation layer. Rardar owns only versioned scene prompts, evidence contracts and response schemas.

The current resolver derives:

```text
provider=openai + model_id=gpt-5.6-sol
  -> internal request_model=openai/gpt-5.6-sol
  -> POST /v1/chat/completions body model=gpt-5.6-sol
```

The API base chooses the endpoint; it is not used to infer provider or capability. An already-prefixed model ID and an explicit `extra_params.litellm_model` have higher resolver precedence but produce the same result when set to `openai/gpt-5.6-sol`.

## Non-normative loopback evidence

This section records the investigation only. Its `0.3` and `1.0` values are not a normative Capability Profile and must not become runtime parameters without applicable real-provider evidence or an explicit operator claim.

The repository-external probe used a random loopback port, a synthetic test key, current LiteLLM and TopicEye's resolver/candidate/provider/call-engine path. It recorded only request path and non-secret JSON fields. Usage persistence and model lookup were replaced with in-memory doubles so no runtime database or configuration was touched.

With synthetic loopback `temperature = 1.0`:

| Case | Internal model | Upstream model | Plain | Medium | Medium + JSON object |
| --- | --- | --- | --- | --- | --- |
| Bare `gpt-5.6-sol` | `openai/gpt-5.6-sol` | `gpt-5.6-sol` | 1 request | 1 request | 1 request |
| Prefixed `openai/gpt-5.6-sol` | same | same | 1 request | 1 request | 1 request |
| Explicit `litellm_model` | same | same | 1 request | 1 request | 1 request |
| Unregistered fake model | prefixed fake | bare fake | 1 request | local reject, 0 | local reject, 0 |

Ten total loopback requests were observed. For the registered GPT-5.6 configuration, LiteLLM forwarded `reasoning_effort = medium`, forwarded `response_format = {"type":"json_object"}`, and converted `max_tokens` to `max_completion_tokens`.

A separate loopback control with explicit `temperature = 0.3` produced one successful plain loopback request, then rejected reasoning-only and structured-reasoning calls before network. The diagnostic identified the local GPT-5 temperature/effort gate. This reproduces the two-step real smoke pattern, and removing `response_format` cannot help while the same reasoning/sampling combination remains. Because the earlier real smoke did not record its effective temperature and no authenticated model-row read was available, `CURRENT_LOCAL_MODEL_TEMPERATURE = UNCONFIRMED`. Loopback `1.0` proves only network emission to the synthetic endpoint; it is not a real model default, provider requirement, or proof of executed reasoning.

Decision: `MODEL_ID_NOT_ROOT_CAUSE`.

Failure location: `LOCAL_BEFORE_NETWORK` for the reproduced blocked request. Confirmed facts are that `provider = openai` is the LiteLLM protocol-adapter label, the resolver derives `openai/gpt-5.6-sol`, the loopback upstream body uses `model = gpt-5.6-sol`, the plain path reaches the network, and the same reasoning rejection occurs without `response_format`. The high-confidence reproduced cause is local parameter assembly/compatibility—not the model ID or `response_format`. The actual local model-row temperature and real-provider support for medium/high/xhigh or native structured output remain unknown.

Non-normative evidence summary:

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

## Prompt and preset audit

| Class | Assets |
| --- | --- |
| `TOPICEYE_ONLY` | Creation/platform prompts, angle recommendation, daily report and digest. |
| `GENERIC_REUSABLE` | Routing, strict JSON, prompt-safety utilities, sanitized errors, cache, logs and usage infrastructure. |
| `RARDAR_ADAPTABLE` | Classification mechanism and prescreen/escalation scaffolding after replacing TopicEye taxonomy, creator language and output schemas. |
| `REJECT_FOR_RARDAR` | Content/academic analysis scoring and creator-oriented enrichment prompts. |

The existing presets and field help assume ordinary Chat Completions, `gpt-4.1-mini`, creator workflows, `temperature = 0.3` and `max_tokens = 2000`. Those remain valid TopicEye product defaults but cannot be treated as universal Rardar reasoning defaults.

## Contracts delivered

- [`RARDAR_AI_ENGINE_ADAPTATION.md`](../platform/RARDAR_AI_ENGINE_ADAPTATION.md) records control-plane ownership, field/request semantics, loopback/root-cause evidence, UI/parameter/prompt audits and the implementation slices.
- [`RARDAR_MODEL_CAPABILITY_PROFILE_V1.md`](../product/RARDAR_MODEL_CAPABILITY_PROFILE_V1.md) defines nine capabilities, including versioned normal/reasoning `free/omit/fixed/unsupported/unknown` temperature policy, `fixedValue` invariants, evidence source/scope, safe persistence and probe rules. The current normative reasoning policy remains `unknown`.
- [`RARDAR_INVOCATION_PROFILE_V1.md`](../product/RARDAR_INVOCATION_PROFILE_V1.md) defines three Rardar-owned scene contracts, policy-governed temperature semantics, parameter merge, strict structured output, cache/failure and prompt-injection boundaries.
- [`RARDAR_LLM_CONTROL_REUSE.md`](../platform/RARDAR_LLM_CONTROL_REUSE.md) is updated to state that the control plane is reused but the AI runtime and capability adaptation are not complete.

Storage decision: `EXTRA_PARAMS_SUFFICIENT`. A versioned `extra_params.capabilities` namespace needs no database migration, but the first implementation must validate the five temperature modes and `fixedValue` rules, reasoning efforts, structured modes, source plus evidence scope; add scoped merge/patch; expose a sanitized API projection; and fail closed for unknown/stale capabilities. Non-normative probe records are not stored in that namespace. The current generic admin payload returns all `extra_params`, including potentially header-bearing LiteLLM settings, so it is not the future capability projection.

## Validation

The iteration requires the existing model-resolver tests, all 27 Rardar LLM control tests, focused prompt-contract tests, the loopback matrix, Markdown reference/anchor/table/fence checks, JSON example parsing, UTF-8, credential-pattern scanning and `git diff --check`. The complete 897-test backend suite is intentionally not part of this docs-only scope.

Local results:

- model resolver/completion-kwargs focus: 7 passed;
- Rardar LLM control boundary: 27 passed;
- prompt and paper-prompt contracts: 5 passed;
- A-D loopback matrix: 10 HTTP requests with the expected local rejection for two fake-model reasoning calls;
- temperature control: one plain loopback request and zero network requests for the two locally rejected reasoning variants;
- five-document Markdown/UTF-8/JSON/credential validation: passed;
- `git diff --check`: passed;
- isolated PostgreSQL test cluster stopped and removed; no TopicEye runtime process was started, stopped or modified by validation.

The exact Draft PR head and GitHub CI result are recorded in the PR body after remote validation. Tests use only isolated test data and loopback/mock providers.

## Safety and non-goals

This iteration changes no Python/TypeScript runtime, frontend, database schema, migration, model configuration, prompt implementation, Rardar response schema, Worker, AIJob, Explosion UI or Find Project behavior. It does not access Production and makes no additional real provider call.

No `drop_params`, silent effort downgrade or new adapter is proposed. Existing factual Rardar pages and rankings remain independent of AI availability.

## Next implementation slices

After human review only:

1. `RARDAR-MODEL-CAPABILITY-PROFILE-01`
2. `RARDAR-INVOCATION-PROFILES-01`
3. `RARDAR-REASONING-COMPATIBILITY-01`
4. `RARDAR-PROMPT-CONTRACTS-01`

The first slice adds strict versioned `extra_params.capabilities`, normal/reasoning five-mode temperature policy, reasoning-effort and structured-output modes, source plus evidence scope/revision, a secret-safe projection, scoped merge/patch, loopback tests and fail-closed unknown handling. It has no new table or migration. The second slice owns the three scene profiles, independent prompt/schema versions, final effective parameter calculation, structured-mode selection, cache identity and stable failures. Only the third slice may perform an authorized real-provider probe and adjust compatibility; it must not add a LiteLLM model-name special case. This iteration does not start any slice.
