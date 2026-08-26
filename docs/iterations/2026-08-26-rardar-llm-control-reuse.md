# 2026-08-26 — Rardar LLM Control Reuse

## Goal and baseline

Establish one reversible call boundary through which future Rardar AI features reuse TopicEye's existing LLM control plane. The branch starts from TopicEye main `eeeddaed75cc7db2e8665706377935c8512b9851`. POC PR #1 at `4422cda3e057827ea4389e04622927ccc6304cce` remains open, Draft, and unmodified. The Rardar repository, Runtime, Production, D1, and real model providers are outside this iteration.

## Existing control-plane audit

| Disposition | Result |
| --- | --- |
| KEEP | Existing `llm_models` management/API/UI, encrypted secrets, LiteLLM provider facade, routing priority, failover/cooldown, retries, rate and concurrency limits, circuit breakers, response cache, `llm_call_logs`, token/cost accounting, JSON mode, and model-test API. |
| ADAPT | Strict route lookup for Rardar, reasoning-effort passthrough and cache identity, strict local JSON/Pydantic validation, stable Rardar errors and scenes, and non-secret provider-error diagnostics. |
| DEFER | Real model configuration/calls, AIJob/Worker, prompts, project summaries/profiles, explosion explanations, Find Project, and Production operation. |
| REJECT | A second provider/client, `RARDAR_LLM_*` configuration, hard-coded provider/base/key/model, Rardar-specific model UI/tables/logs, or wholesale provider code copied from another repository. |

The current schema and frontend already expose the generic routing group, so no model-management UI change, table, or migration is required.

## Implementation

- Added `app.services.rardar_llm_control` with three scenes, the fixed logical `rardar` route, optional `medium`/`high`/`xhigh` effort, stable errors, and sanitized result metadata.
- Added opt-in strict lookup to the existing model cache. Existing TopicEye callers keep their prior fallback behavior, while Rardar cannot borrow the `default` route.
- Extended the existing provider/call engine so effort reaches LiteLLM unchanged and participates in shared cache identity and safe logs.
- Added prompt version, schema version, and Pydantic schema digest to structured-call cache identity.
- Added strict JSON decoding and caller-owned Pydantic validation without creating a parallel request path.
- Replaced raw upstream exception persistence/return in the shared call path and model-test endpoint with non-secret operational categories.
- Switched shared LLM admission telemetry and response-cache expiry to a high-resolution monotonic clock so short waits/TTLs remain observable on Windows; no admission or expiry policy changed.
- Added a dedicated Linux CI job that uses only a fake bottom provider and requires no API key or network model call.

## Test and safety contract

Focused tests exercise real TopicEye routing, retry/failover, rate/concurrency entry points, circuit breaker, response cache, model configuration rows, encrypted-key decryption at the bottom call, call-log persistence, and Rardar error mapping. Only the bottom `acompletion`/model-test provider call is replaced.

Coverage includes one/multiple/disabled/changed route models, priority and same-group failover, no fallback to `default`, all effort values and invalid effort, cache partitions, valid/fenced UTF-8 JSON, duplicate keys, non-finite values, type/required/extra-field failures, timeout/429/5xx/circuit states, key/prompt/response non-leakage, and unchanged Explosion facts after an AI failure.

Full backend, existing LLM, Adapter, PostgreSQL migration, frontend, layering, dependency, and audit results are recorded in the Draft PR. Tests write only isolated databases and temporary fixture copies. No real credential, model call, Rardar file, business fact, or Production resource is used.

## Non-goals and next step

This iteration does not configure a model, add AI content, change Today, implement a Worker/queue, alter Prompt management, deploy, or modify POC PR #1. The next step after human review is the separately authorized local configuration and smoke-test task; it is not started here.
