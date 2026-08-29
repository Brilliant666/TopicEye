# 2026-08-29 — Rardar Today Content Quality and Detail IA Reset

## Goal

Make Today understandable in five seconds and a project detail useful for an
adoption decision in ten seconds. The iteration fixes semantic profile quality
before changing presentation: project identity, core value and differences are
now distinct, evidence-backed layers, while raw excerpts and audit metadata no
longer lead the product reading path.

## Baseline evidence

The repository-external audit of the real Top 20 reproduced the failure modes
that field-presence validation had missed:

- 0 ready, 15 partial and 5 rejected semantic profiles;
- a raw image/HTML summary, a bare attachment URL and a README redirect notice;
- two long English summaries and two placeholder capability sets;
- no profile had an explicit, evidence-backed core value.

The audit is read-only, records the repository, source and language, identity,
core value, capability count, stable issue codes and repair path, and fails the
build contract when unsafe main-path content survives.

## Serving Profile v4

Serving v4 adds the following layers while retaining v1/v2/v3 reads:

- `identitySummaryZh`: a concise definition of what the project is;
- `coreValueZh` plus `coreValueEvidenceRefs`: why it is worth opening;
- `keyDifferentiators`: no more than two evidence-backed differences;
- `capabilities`: the full structured capability set for detail;
- `qualityState` and `qualityIssues`: `ready`, `partial` or `rejected` based on
  semantic validity rather than field presence.

The generic sanitizer removes image/HTML attributes, badges, bare URLs,
navigation and migration notices, code/install-only blocks and placeholders.
Useful feature and use-case lists remain available. A redirect README can
follow at most two explicit repository-local paths; path traversal, missing
targets and external navigation fail closed. Evidence sections are ordered by
their numeric source position and bounded before model input.

For English or incomplete evidence, the existing `routing_group=rardar` model
produces a constrained Chinese identity, core value and capabilities. Output is
accepted only after strict JSON, Schema, evidence-ref, deduplication and source
revision checks. Model failure yields safe partial facts and never blocks
Serving publication. There are no repository-specific conditions.

An isolated real rebuild produced Serving generation
`20260828T001104828269Z-aea4f42ac953--acde1ebbda3e5d7a`. The after-audit found
19 ready, 1 safe partial and 0 rejected profiles. All Top 20 identities and core
values are clear Chinese; URL, image/HTML, redirect, long-English, placeholder,
empty/unreferenced core value, duplicate title/detail and invalid evidence-ref
counts are all zero. The remaining partial state is a non-visible supporting
capability language issue; its main identity, core value and displayed signals
are safe Chinese.

## Product hierarchy

Today no longer presents three equal capability boxes. Each ranked card now
orders information as repository and 24-hour delta, identity and product form,
highlighted core value, then at most two differences/capabilities. Rejected
profiles expose only safe repository and objective facts.

Project detail now follows this order:

1. one identity Hero with product form, environment, delivery and two Today facts;
2. core value and up to two differentiators;
3. the full capability narrative;
4. Rardar adoption and optional AI analysis;
5. at most four primary start-here links, with remaining links collapsed;
6. centralized 24-hour facts;
7. closed-by-default official excerpts and generation provenance.

The project identity, rank, delta and Find Project CTA are not repeated. AI is
limited to differentiation, reusable assets, cost, scenarios and implementation
boundaries; it does not redefine the project or repeat ranking facts.

## Boundaries and verification

Normal Today and detail reads continue to use the immutable static Serving
projection: zero GitHub calls, zero LLM calls and zero raw-source reads. Only
sync/rebuild may obtain README evidence or run the existing model route. The
iteration adds no table or Alembic migration, changes no model/API/routing
configuration, and does not access Production.

Behavior coverage includes sanitizer and redirect safety, semantic quality
states, core/differentiator evidence, v1/v2/v3 compatibility, corrupt-profile
fail-closed behavior, Top 20 audit, Today hierarchy, rejected fallback, detail
ordering and deduplication, evidence default state, AI boundaries, responsive
375/768/1440 layouts and production-build Playwright flows.

Rollback is an application rollback and Runtime restart to the retained healthy
Serving generation. No database down migration or data rewrite is required.
This iteration does not begin `RARDAR-DISCOVER-REALTIME-01`.
