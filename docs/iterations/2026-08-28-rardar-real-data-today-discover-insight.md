# 2026-08-28 — Rardar Real Data, Today/Discover and Project Insight

## Goal

Replace the local Rardar product's implicit demo path with a fail-closed,
audited copy of the current published Rardar Explosion Artifact. Present exact
24-hour facts and incomplete observations separately, then add evidence-bound
project insight and a safe hand-off into Find Project without changing
TopicEye's model control plane.

## Read-only Production source

The implementation was exercised against the Production generation
`20260827T000708332719Z-0f9e8641c14e` through the configured `rardar-prod` SSH
target. Production was inventory-only: no D1 access, service restart, refresh,
environment change, credential read or filesystem write occurred. The source
manifest was `ready`, its 68 declared artifacts and source hashes validated,
and the Explosion Artifact reported a `warming_up` window with 0 exact and 500
pending projects. That state is intentionally rendered as facts rather than
filled with demo projects or extrapolated ranks.

## Audited local mirror

- `scripts/rardar-local.ps1 sync-data` invokes a dedicated read-only sync CLI.
- One remote read builds a stable pointer/manifest/artifact inventory and
  verifies the manifest digest, required artifact hashes, source copies and
  generation identity before any local publication.
- A generation is staged and validated below the repository-external
  `%LOCALAPPDATA%\TopicEye\rardar-intelligence` mirror. Publication is a single
  atomic local pointer replacement; immutable generations make the same sync
  idempotent.
- Locks, no-follow path checks, junction/symlink rejection, bounded payloads,
  rollback and interruption cleanup prevent partial or escaped publication.
- Provenance records the non-secret source host identifier, sync time and
  manifest/artifact hashes. It never stores a credential or remote command
  output.
- Missing or invalid real data returns the explicit `not_synced`/fail-closed
  state. Demo mode requires `RARDAR_DATA_MODE=demo` and cannot activate in
  Production.

## Product behavior

- **Today** contains only Artifact `exactTop20` rows, preserves
  `observedStarDelta DESC`, `totalStars DESC`, `repository ASC`, defaults to 10
  rows and expands to at most 20. While the natural 24-hour baseline is not
  ready, it shows an honest empty state and links to Discover.
- **Discover** contains only Artifact `pending` rows, preserves `pendingRank`,
  displays at most 20, and labels discovery stage solely from the observed
  window duration. It never linearly projects a short observation to 24 hours.
- Coverage totals, successful source queries, degraded sources, generation,
  source hashes and local sync time remain visible without claiming whole-
  GitHub coverage.
- Each project can open `/find?repositoryUrl=<canonical public GitHub URL>`.
  The server validates exactly one public `github.com/<owner>/<repository>`
  URL, the client visibly acknowledges the imported repository, and refresh
  preserves it. Extra paths, credentials, query strings and traversal forms
  are rejected instead of guessed.

## Evidence-driven AI insight

Project insight uses TopicEye's existing strict `rardar` model route and does
not introduce a provider, key, model or routing setting. The evidence collector
makes at most four bounded public GitHub API requests for repository metadata,
README, top-level contents and latest release. It does not clone or execute a
repository.

The AI input excludes rank, stars and internal observation state. The strict
result contains an official introduction (or clearly labelled Chinese
translation), one to three core highlights, reusable assets, concrete
start-here paths, evidence references and only verified implementation
boundaries. Structured output falls back to plain JSON only when locally parsed
and schema-validated. Unknown evidence references, invented paths, generic risk
phrases and fact repetition fail closed. If AI is unavailable, the factual card
and deterministic official introduction remain available; no free-text model
fallback is published.

Evidence is cached for 15 minutes by repository plus Artifact revision. AI
cache identity includes the evidence digest and prompt/schema versions, so a
changed README or source generation cannot reuse a stale explanation.

## Validation and rollback

Behavior tests cover sync idempotency, remote instability, path safety,
interruption recovery, real/demo/not-synced states, ranking separation,
bounded evidence, strict AI validation, cache invalidation, Find URL safety and
responsive server-rendered pages. Validation uses temporary databases, random
loopback ports and temporary data directories; it does not write the local
Runtime database or Production.

Rollback is an application rollback and restart. The external mirror is
immutable and may retain the last verified generation; old code does not read
it. No database migration, down migration, Production action or model
configuration rollback is required.

This iteration does not implement the two-hour observer, create exact facts,
publish a Rardar generation, change Production, deploy, redesign unrelated
TopicEye/Admin pages or begin the next product objective.
