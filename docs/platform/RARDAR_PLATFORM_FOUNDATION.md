# Rardar Platform Foundation

## Status and provenance

This document defines the first formal TopicEye × Rardar platform-fusion boundary.

- Secure TopicEye fork baseline: `f1c80188de7f05ba4285de48f962b7b31656d930`.
- TopicEye upstream provenance: `fxbin/TopicEye` at `8b559895c6e3547550a85ac561cfee4a42113448`.
- Executable POC evidence: PR #1, head `4422cda3e057827ea4389e04622927ccc6304cce`.
- Rardar visual/product reference: `Brilliant666/rardar` at `e21c5e258c63140ff941434e0f57514893258b42`.
- Direction: `TopicEye inside / Rardar outside`.

The POC remains an evidence branch. This foundation neither merges it nor depends on it being merged.

## Promote Matrix

| Classification | Decision |
| --- | --- |
| `PROMOTE_NOW` | Strict centralized Product Profile; Rardar wordmark, header and six-item navigation; scoped blue-white tokens; responsive user shell; honest route empty states; Admin and default TopicEye compatibility boundary. |
| `DEFER` | Find Project APIs; durable AI Job and Worker; AI business prompts/results; product diagnostics; source/report/scheduler integration. The read-only Explosion Adapter and the provider-neutral LLM control reuse boundary were promoted in separate follow-ups. |
| `POC_ONLY` | Explosion A/B fixtures and pointer; Mock Sub2API and failure scenarios; two POC PostgreSQL tables; migration `4d8a71c9f201`; simulated Job progress/candidates; POC screenshots and diagnostics endpoints. |
| `REJECT` | Scattered environment checks; duplicated or global Rardar colors; hard-coded fixture/data paths; fake projects, Star counts or Job states; mapping repositories into TopicEye content; POC-only compatibility bypasses. |

Promotion is semantic and selective. No POC directory was copied wholesale.

## Central Product Profile

`RARDAR_PRODUCT_MODE` is the only activation input.

| Input | Active profile |
| --- | --- |
| unset, empty or `false` | TopicEye |
| `true` | Rardar |
| any other value | fail closed during backend settings validation and frontend build/config loading |

Values are trimmed and case-insensitive, but aliases such as `1`, `yes`, `enabled` and `rardar` are rejected. Frontend and backend both expose `topiceye` / `rardar`, the same six navigation paths and the same literal boolean boundary.

Changing the profile requires a backend restart and a fresh frontend build/start. It is not a per-request or browser-side toggle.

Central implementation points:

- Backend: `app/core/config.py` and `app/core/product_profile.py`.
- Frontend build boundary: `product-profile.config.js` and `next.config.js`.
- Frontend consumer boundary: `src/lib/product-profile.ts` and `ClientLayout`.

No business API was added for profile discovery.

## Visual boundary

Rardar user pages use a scoped CSS Module rather than changing TopicEye's global theme. The `.product` boundary owns the formal tokens:

- brand primary and secondary;
- background and surface;
- border;
- muted and strong text;
- success, warning and danger;
- radius and shadow;
- container width, header height and spacing.

The shell carries the Rardar wordmark, horizontal desktop navigation, touch-sized mobile navigation, blue-white surfaces, large hero, light borders, rounded cards and explicit status pills. TopicEye user pages and Admin are outside this scope and retain their original theme.

## Route and Admin boundary

| Path | Rardar policy | Result |
| --- | --- | --- |
| `/` | `ALLOW` | Today foundation shell, internally rewritten to the Rardar home implementation. |
| `/activity` | `ALLOW` | Activity slot. |
| `/discover` | `ALLOW` | Discovery slot. |
| `/find` | `ALLOW` | Find Project slot. |
| `/candidates` | `ALLOW` | Candidate-pool slot. |
| `/watchlist` | `ALLOW` | Watchlist slot. |
| `/admin` and descendants | `HIDE_FROM_NAV` | Existing TopicEye Admin layout and authorization boundary. Never wrapped in Rardar chrome. |
| `/login`, `/oauth/callback` | `HIDE_FROM_NAV` | Existing chromeless system flow. |
| legacy TopicEye content routes while Rardar is active | `REDIRECT` | The old page is not mounted inside Rardar chrome; the client returns to `/`. |
| Rardar-only routes while TopicEye is active | `NOT_FOUND` | Route files remain installed but do not become TopicEye product pages. |

Default TopicEye mode keeps the original root page, title, navigation, content routes, Admin, APIs, source management, reports, users and permissions. The Rardar Adapter route is not registered and no Rardar filesystem read occurs in this profile.

## Honest capability slots

The foundation created three named insertion points. The first and the provider-neutral part of the third now have separate, reversible follow-ups; product AI remains empty:

1. `Intelligence Adapter` — read-only audited Explosion Artifact reader; see `RARDAR_INTELLIGENCE_ADAPTER.md`.
2. `Find Project Control Plane` — future RequirementProfile and durable Job boundary.
3. `AI Runtime` — Rardar now has a minimal strict call boundary over TopicEye's existing LLM control plane; see `RARDAR_LLM_CONTROL_REUSE.md`. Real model configuration, queue, isolated Worker, prompts and AI artifacts remain deferred.

The remaining empty routes state that their capability is not connected. Today renders only verified Rardar facts; it does not call the new LLM boundary. There are still no POC fixture projects, simulated candidates, fake progress, real model configuration, network AI requests or database writes.

### Discover product direction

The docs-only Gold review, calibration, and structured-output recovery define
the future Discover user job
as “which projects outside Today Top 20 are worth looking at now?” Rardar's
stages, deltas and acceleration remain authoritative facts, while TopicEye
separates Scope, momentum-blind Value, and Timeliness. The model does not own the
final decision or Primary Reason. A deterministic matrix and fixed reason
precedence run before separate duplicate/capacity packing. The normative Gold
v3 contains 36 provisional projects: exactly 9 approved product-boundary
decisions and 27 unreviewed labels. The original Holdout is revealed historical
evidence. A separately frozen, zero-overlap 24-project Fresh Holdout passed all
gates. PR #26 accepts only the contract; after its exact reviewed revision is
merged, the next step is a separate Local/Shadow Selection Runtime
implementation. The current momentum-stage runtime remains unchanged and
Production Discover remains unactivated.

## Code ownership and upstream sync hotspots

Migrated from the POC as validated semantics:

- one explicit Product Profile;
- six-item Rardar information architecture;
- separate Rardar and Admin chrome;
- responsive blue-white product direction.

Rewritten for the formal foundation:

- profile validation and route-visibility contract;
- Rardar components and scoped design tokens;
- all page content and honest empty states.

Not adopted from the POC (the later formal Adapter was independently rewritten against real contracts):

- POC artifact adapter and fixtures, provider/runtime, Worker, models, migration, repositories, Job UI and diagnostic UI.

Likely upstream rebase conflict hotspots:

- `frontend/src/app/layout.tsx`;
- `frontend/src/components/ClientLayout.tsx`;
- `frontend/next.config.js`;
- `backend/app/core/config.py`;
- the deliberately introduced read-only Adapter route in `backend/app/api/v1/rardar.py`.

The Apache-2.0 license and upstream history remain intact.

## Rollback

This foundation has no schema migration, business data, AI artifact or Production configuration.

Rollback is a normal revert of the foundation commit. TopicEye remains the default profile, the Rardar shell disappears, no database downgrade is required and user data is unaffected.

## Foundation validation

The exact candidate tree was validated against PostgreSQL 16.15 and a Linux Python 3.12 environment:

- backend lint, format, layering and 897/897 pytest cases passed;
- Alembic `c003bd551911` passed from a fresh database and a repeated upgrade was a no-op;
- frontend TypeScript, 161/161 Vitest cases, coverage gates and both production profiles passed;
- default TopicEye HTTP retained its title, root, content and Admin boundaries while Rardar-only routes returned 404;
- all six Rardar routes returned 200 and Admin remained outside the Rardar shell;
- Chromium checks passed for Today, Find Project, Activity and Admin at 375 × 812, 768 × 1024 and 1440 × 900;
- normalized PostgreSQL data exports before and after Rardar page access were byte-equivalent;
- `pip check`, `pip-audit` and `npm audit` reported no application dependency vulnerabilities.

Production RSS snapshots after comparable route warm-up were 79.9 MB frontend, 414.6 MB backend and 256.1 MB PostgreSQL for TopicEye, versus 76.3 MB frontend, 425.5 MB backend and 280.3 MB PostgreSQL for Rardar. These are single local snapshots, not capacity guarantees; the isolated Rardar frontend shell itself did not add measured frontend RSS. There is no Worker in this stage.
