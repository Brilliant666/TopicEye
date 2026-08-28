# 2026-08-28 — Rardar Today Static Serving and Project Detail

## Goal

Turn the audited Rardar Explosion Artifact into a fast local product flow:
Today explains each project from official evidence, the repository link opens
an immutable internal detail, AI analysis is explicitly requested there, and
Find Project receives a safe canonical repository URL. Normal page reads must
not repeat the raw Artifact audit or contact GitHub/LLM.

## Immutable Serving Projection

The repository-external local mirror now has an independent `serving/` tree:

```text
serving/current.json
serving/generations/<serving-generation>/manifest.json
serving/generations/<serving-generation>/today.json
serving/generations/<serving-generation>/projects/<github-repository-id>.json
serving/generations/<serving-generation>/evidence/<github-repository-id>.json
```

Serving schema v1 binds the source generation, raw manifest SHA-256 and
Explosion Artifact SHA-256. Its ready manifest inventories the Today, project
and evidence files with byte sizes and SHA-256 values. Strict Pydantic models
and cross-file checks additionally bind numeric repository identity,
repository name, source generation, profile evidence digest, README revision
and every evidence/start-here reference.

The Serving generation ID is content addressed from the source generation and
canonical projection content. A repeated build with unchanged README/profile
evidence is a true no-op. The installer stages immutable files, verifies the
complete package and atomically replaces `serving/current.json`. Sync installs
raw and Serving generations together and restores both previous pointers if
either activation fails, preventing mixed-generation reads.

The in-process loader checks `serving/current.json` for each request, then
reuses a validated DTO bundle by pointer identity. It reloads on pointer change
under one lock. Current and retained-generation reads fail closed on pointer,
manifest, hash, Schema, identity or evidence corruption; they never fall back
to raw or demo data.

## Official Top 20 profiles

Profiles are built before activation, never during a page request. The bounded
GitHub client selects an official Chinese README first, otherwise the default
README, then GitHub Description or a clearly labelled restricted fallback. It
does not clone or execute repository code, read the GitHub CLI OAuth token, or
persist headers/tokens.

The Markdown parser is section-aware, preserves useful lists and rejects
badges, navigation, logo-only warnings, sponsors and contributor noise. Each
Chinese summary, capability, use case and delivery form carries evidence refs
to the saved README section or official metadata. Start-here links are built
only from verified README anchors and real tree paths; file paths use `/blob/`
and directories use `/tree/`, with traversal and unsafe repositories rejected.

English evidence is translated through TopicEye's existing strict
`routing_group=rardar` route. The structured prompt contains the exact JSON
shape; Rardar still performs local JSON, Schema and evidence-ref validation.
The persistent profile cache is keyed by numeric repository ID, evidence
digest, profile Schema, prompt version and requested translation state. Model
unavailability yields official original text and a retryable partial profile
without blocking Serving activation.

The real Top 20 smoke produced 20 records: 14 complete, 6 partial and 0 source
unavailable. All Top 10 summaries are understandable Chinese. The Gold sample
`tt-a1i/archify` uses `README_ZH.md` at blob
`60924c890efed7a199ba96f1a9b5a38127d9976f` and correctly captures interactive
architecture deliverables, snapshot comparison, evidence/path tracing and
standalone HTML/PNG/SVG/WebM output.

## Product and API behavior

- `GET /api/v1/rardar/today` returns the compact Serving Today DTO.
- `GET /api/v1/rardar/projects/{githubRepositoryId}?generationId=...` returns
  one immutable project/profile/evidence DTO.
- `POST /api/v1/rardar/projects/{githubRepositoryId}/insight` requires the same
  generation and uses only the saved static evidence.
- The compatibility Explosion endpoint also reads Serving rather than auditing
  source captures.
- Successful GET responses emit ETag and
  `private, max-age=15, stale-while-revalidate=45`. Next uses a five-second
  revalidation window instead of unconditional `no-store`.
- `/api/health` is a lightweight frontend liveness endpoint and does not load
  business data.

Today remains an objective `observedStarDelta` list, defaults to Top 10 and can
expand to Top 20. Cards show official summaries and up to four evidenced
capabilities. Embedded AI and Find actions were removed. The internal route is
`/project/github/<numeric-id>?generation=<source-generation>`; repository text
is display-only identity.

The detail SSR shows the official profile, excerpts, README revision, evidenced
capabilities, verified start-here links and exact Today facts. It calls neither
GitHub nor LLM. AI deep insight is optional and failure does not hide facts.
The Find CTA preserves the existing dual-input flow and pre-fills only the
canonical public GitHub URL.

## Real performance and visual validation

The previous raw-adapter request path took roughly 7.0–7.4 seconds and read 13
raw source copies per request. Against an isolated copy of the real mirror, the
new production-mode results were:

| Surface | warm p50 | warm p95 |
|---|---:|---:|
| Backend Today API | 25.18 ms | 31.16 ms |
| Backend project API | 37.82 ms | 40.40 ms |
| Production homepage SSR | 134.94 ms | 141.88 ms |
| Production project detail | 50.52 ms | 66.58 ms |
| Frontend health | 12.54 ms | 13.49 ms |

Twenty repeated Today requests used the Serving cache and read zero source
capture copies. Ten repeated homepage/detail loads made zero GitHub and zero
LLM requests. Browser and Playwright validation at 375, 768 and 1440 pixels
found no horizontal overflow, React overlay or console error; Top 20 expansion,
internal detail navigation, static evidence, AI action state and Find prefill
were present.

## Verification and rollback

Behavior tests cover raw-to-Serving projection, strict hash/Schema/source
binding, deterministic no-op rebuild, README selection and parsing, translation
and caches, GitHub/LLM degradation, pointer interruption/rollback, mixed
generation rejection, concurrent load/cache invalidation, static-evidence AI,
HTTP status mapping, SSR states, responsive navigation and path safety.

Validation uses temporary data directories, isolated PostgreSQL databases and
random loopback ports. It does not modify the Runtime mirror, Production, D1,
scheduler, model credentials or route configuration. The existing model route,
provider, model, API base/key, priority and usage log mechanism remain in place.

Rollback is an application rollback plus Runtime restart. The last immutable
healthy raw/Serving generations remain external to Git. If a rebuild fails,
the previous paired pointers stay active. No database down migration,
Production action or model configuration rollback is required.

This iteration does not deploy TopicEye, change Production, trigger Observation
or Refresh, redesign unrelated TopicEye/Admin pages, or begin
`RARDAR-DISCOVER-REALTIME-01`.
