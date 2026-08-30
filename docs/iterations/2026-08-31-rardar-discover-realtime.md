# 2026-08-31 — Rardar Discover Near-real-time Product Closure

## Goal

Close the product loop from Rardar's audited two-hour Observation facts to a
real TopicEye Discover experience without introducing another observer,
scheduler, database fact table, ranking model, provider, or AI worker.

## Producer contract

Rardar merge `b99a8b88a9b46b830f5170824a7c90ead41cc51a` adds immutable
`TrendingDiscoverArtifact v1`, full source/Today exclusion audit, atomic
publication and rollback, scheduler ordering and bounded telemetry. TopicEye
vendors that exact contract and records every source and local hash.

## Consumer and publication boundary

The raw adapter revalidates the entire producer proof, including every capture
copy and a mechanical stage/order recomputation. Sync then builds a separate
Discover Serving generation. At most ten items from each stage are enriched in
producer order. Every selected item must pass the existing profile and evidence
quality gates before any pointer changes.

Today and Discover use independent raw and Serving pointers. Repeated sync is
idempotent. A profile, write, validation or activation failure leaves the
previous Discover Serving intact and cannot alter Today.

## Product result

`/discover` is now the near-real-time surface for facts that have not yet
formed a complete Today exact window. It presents 刚刚发现、持续升温 and
接近验证 as sections, not a global rank. Every Star delta states its actual
observed hours. Coverage and degraded sources remain inspectable without
dominating the page.

The existing project-detail component accepts a generation-bound Discover
source. It preserves the static identity, positioning, capabilities and
evidence hierarchy while replacing Today rank/baseline facts with Discover
stage and actual Observation facts. AI insight is opt-in and reuses TopicEye's
current Rardar control plane; facts and order never depend on it.

## Non-negotiable boundaries

- no new D1 or PostgreSQL table and no migration;
- no Production write, derive, restart, service, timer or deployment;
- no hidden fixture or Demo fallback;
- no page-time GitHub, LLM or raw-artifact reads;
- no Today schema, rank, profile, detail or UI change;
- no model-route or credential change.

## Verification contract

Backend behavior covers strict raw reads, source/Today binding,
recomputation, tamper and unstable-path rejection, Serving completeness,
idempotent sync, activation rollback, pointer switching, stale/empty/error API
states and Today pointer isolation. Frontend behavior covers all three stages,
actual windows, stale/error/empty states, coverage, internal detail, AI and Find
Project actions. Final delivery also requires full backend and frontend
regression, both product builds, migrations, security checks, exact-head CI and
375/768/1440 browser acceptance against the isolated real-data mirror.

Production scheduler activation remains a later, explicit operation:
`RARDAR-DISCOVER-RUNTIME-ACTIVATION-01`.
