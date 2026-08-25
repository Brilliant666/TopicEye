# 2026-08-25 — Rardar Platform Foundation

## Goal

Establish a formal, minimal Rardar Product Profile and user-facing shell on secure TopicEye main while preserving TopicEye default behavior and Admin boundaries.

## Baselines

- TopicEye secure main: `f1c80188de7f05ba4285de48f962b7b31656d930`.
- POC evidence: PR #1 at `4422cda3e057827ea4389e04622927ccc6304cce`.
- Rardar visual baseline: `e21c5e258c63140ff941434e0f57514893258b42`.

## Promote Matrix

- `PROMOTE_NOW`: Product Profile, header/navigation, scoped tokens, responsive shell, six route shells, Admin isolation and TopicEye compatibility tests.
- `DEFER`: Intelligence Adapter, Explosion and Find Project APIs, Job, AI Runtime/Worker, scheduler, source/report integration.
- `POC_ONLY`: fixtures, Mock Sub2API, failure simulation, POC tables/migration, candidate and Job simulation, diagnostics and screenshots.
- `REJECT`: scattered flags, duplicated tokens, fake data, fixture paths, repository-to-content mapping and POC-only bypasses.

The authoritative expanded matrix is in `docs/platform/RARDAR_PLATFORM_FOUNDATION.md`.

## Implementation

- Strict `RARDAR_PRODUCT_MODE` parsing in frontend and backend; TopicEye is default and invalid values fail closed.
- One frontend profile supplies navigation and route visibility.
- One backend profile supplies the matching product identity and navigation contract.
- Rardar CSS Module contains all blue-white design tokens and leaves TopicEye/Admin global styles unchanged.
- Six user routes render explicit foundation states; `/` uses an internal build-time rewrite without replacing TopicEye's root source page.
- Rardar mode redirects legacy TopicEye content before its child page is mounted; Admin/login/OAuth stay on the TopicEye compatibility boundary.
- No API, table, migration, fixture, provider, Worker or scheduler was added.

## Validation record

- Exact candidate tree on Linux/Python 3.12: Ruff, format, layering and 897/897 pytest cases passed.
- PostgreSQL 16.15: fresh Alembic upgrade to `c003bd551911`, repeated no-op upgrade and backend startup passed in both Product Profiles.
- Frontend: TypeScript passed; 161/161 Vitest cases passed; statement/branch/function/line coverage was 95.34%/92.38%/100%/95.52%; TopicEye and Rardar production builds passed.
- HTTP: default TopicEye root, content and Admin routes returned 200 with the original title; the five Rardar-only route files returned 404. In Rardar mode all six product routes and Admin returned 200.
- Chromium: Today, Find Project, Activity and Admin passed at 375 × 812, 768 × 1024 and 1440 × 900 with no horizontal overflow, correct responsive navigation and no Rardar shell around Admin.
- Data: normalized PostgreSQL data-only exports before and after Rardar browser access were identical. No external AI request was made.
- Security: `pip check`, `pip-audit`, `npm audit`, credential-pattern and UTF-8 checks passed; the audited pins remain FastAPI 0.133.0, Starlette 1.3.1 and cryptography 50.0.0.
- Existing non-gating baseline: the repository-wide ESLint command reports 24 pre-existing errors outside the changed paths. Required TypeScript, test, coverage, build and GitHub checks remain authoritative for this stage.

## Resource snapshots

| Profile | Frontend RSS | Backend RSS | PostgreSQL RSS |
| --- | ---: | ---: | ---: |
| TopicEye | 79.9 MB | 414.6 MB | 256.1 MB |
| Rardar Foundation | 76.3 MB | 425.5 MB | 280.3 MB |

The observed total snapshot delta was +31.5 MB; PostgreSQL and backend values include request-warmup variance. The Rardar frontend shell measured 3.6 MB lower than TopicEye in this single production snapshot, so no frontend RSS increase is attributed to the shell. Worker RSS is 0 MB because this stage adds no Worker.

## Visual acceptance

- Desktop header uses the six approved horizontal navigation items.
- Mobile navigation exposes the same six items with touch-sized targets.
- Rardar uses a bright blue-white presentation with a large hero, rounded surfaces and explicit unconnected states.
- TopicEye and Admin do not inherit the Rardar shell or tokens.

## Security and data

- Security pins remain FastAPI `0.133.0`, Starlette `1.3.1` and cryptography `50.0.0`.
- Database tables added: `0`.
- Alembic migrations added: `0`.
- Business writes from Rardar shell: `0`.
- Real AI/OAuth/Production calls: `0`.

## Non-goals

No artifact adapter, ranking, Find Project workflow, AI provider, queue, Worker, source, scheduler, user migration, D1 migration or Production deployment is included.

## Rollback

Revert the foundation commit. No database or data rollback is required.

## Next

After this Draft PR passes review and is merged in a separate task, the next bounded goal is `RARDAR-INTELLIGENCE-ADAPTER-01`.
