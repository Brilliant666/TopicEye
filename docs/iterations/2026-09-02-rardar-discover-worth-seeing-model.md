# 2026-09-02 — Rardar Discover “值得看” Product Model

## Goal

Define, with current real evidence, what “worth seeing now” means outside Today
Top 20 before writing a new selection runtime.

## Evidence and scope

The research used Rardar main
`34556a3ce4765acdc6a91f6fc895846aa33ee5f2`, TopicEye main
`dfd9045cc6a647d2832b28ae8bb596ddaa630d39`, the canonical 2026-09-01
16:00 UTC Observation and Today generation
`20260901T001939007155Z-fe663ec7b844`. Production access was read-only; D1,
secrets and business writes were not accessed.

The complete eligible universe contained 461 projects. Sixty projects were
split evenly across high momentum, low-momentum/high-value hypotheses, new or
low-base projects, mature low-timeliness projects and negative/noise
hypotheses. Every sample has a bounded README, tree and Rardar fact package;
39 also have release evidence. The 24-project Gold Set is explicitly
provisional and awaits user review.

## Product decisions

- Discover is a worth-seeing-now selection, not a momentum ranking.
- Rardar facts remain immutable authority; TopicEye owns evidence-bound
  semantic selection.
- Momentum is auxiliary and cannot be a Primary Reason.
- Five value reasons, six deterministic timeliness signals and nine reject
  reasons are fixed for v1.
- `SELECT_NOW` requires value, high confidence and a strong deterministic
  why-now path.
- Broad deterministic recall (30–60) is separated from semantic selection
  (target 10–20, possibly fewer or empty).
- Near-duplicates are capped before diversity packing; diversity never fills a
  weak slot.
- IA A, a single unranked curated stream with category/reason filters, is the
  recommended page structure.

## Real model probes

The existing TopicEye `routing_group=rardar` route and configured
`gpt-5.6-sol` model were used without provider, model, key, temperature or
reasoning-effort changes. Eighty top-level calls were the hard cap. Twelve
identical repeats hit the existing cache and were not misreported as independent
consistency; twelve additional calls used a separate research prompt-version to
obtain real provider repeats.

Model C (value plus timeliness) is the correct contract shape but did not meet
implementation gates. It achieved 100% eventual primary structured results and
100% evidenceRef validity, but only 35% `SELECT_NOW` precision, 66.67%
high-growth/low-value false positives, 0% `WORTHWHILE_NOT_NOW` accuracy and 50%
Primary Reason repeat consistency. Per-attempt structured success was 90%.

The failure is product-significant: the prompt asked the model to interpret raw
timestamps, so it treated first appearance in a six-day-old Capture store and
ordinary repository activity as “now”. The v1 contract therefore moves all
timeliness computation to deterministic code and supplies only validated signal
IDs to the model.

## Delivery

- product model;
- strict output contract;
- 60-project sample audit;
- sanitized 24-project provisional Gold JSON;
- platform/adapter clarification that momentum is auxiliary;
- docs-only Draft PR.

No runtime, frontend, database, migration, Rardar, model configuration or
Production data was changed. Implementation and Production activation remain
separate tasks.

## User review required

The remaining questions are decisions for product review, not hidden
implementation defaults: confirm or revise the 24 provisional Gold labels, the
five Primary Reasons, the four strong why-now paths and IA A's single-stream
presentation. Any revision must update the versioned policy and Gold evidence
before the implementation evaluation begins.

## Readiness

The research task is complete, but
`READY_FOR_RARDAR-DISCOVER-WORTH-SEEING-SELECTION-01 = NO`. The next selection
iteration must implement deterministic timeliness, batch duplicate context and
confidence gates, then rerun the same Gold evaluation until all thresholds pass.
