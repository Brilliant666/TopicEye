# Rardar Intelligence Adapter

## Status and scope

This contract connects TopicEye's formal Rardar product profile to the audited 24-hour GitHub Explosion Artifact published by `Brilliant666/rardar`. It is a read-only integration: Rardar remains the fact authority and TopicEye remains the presentation platform.

The first release reads one published generation, exposes `GET /api/v1/rardar/explosion-board`, and renders the exact Top 5 plus at most three first-seen candidates on the Rardar home page. It does not implement AI, Find Project, a scheduler, an observer, a database mirror, a cache, or Production deployment.

Source baseline: Rardar merge `cb92274d5c3d3f8f17ab7f87b708040cc3635620` (`Publish audited 24-hour GitHub explosion artifacts (#28)`).

## Activation contract

Two backend settings have distinct responsibilities:

- `RARDAR_PRODUCT_MODE=true` activates the Rardar product profile. TopicEye remains the default.
- `RARDAR_INTELLIGENCE_DATA_DIR` identifies the Rardar `data/` root. It is backend-only and has no default fixture or repository-relative fallback.

The data path must be absolute and normalized. Every existing component from the filesystem anchor through the requested file must be a normal directory or regular file. Symbolic links, junctions, reparse points, `..`, backslashes in generation-relative paths, and path escape are rejected.

An empty data setting does not prevent backend startup. The Rardar API returns `503 rardar_intelligence_not_configured`, and the page displays “情报数据尚未配置”. A configured but missing root returns `503 rardar_intelligence_unavailable`. Default TopicEye mode returns 404 for the Rardar API and does not read the Rardar filesystem.

## Exact-generation read protocol

One request performs one logical pointer read and binds all subsequent work to its `generationId`:

1. perform a bounded stable read of `current.json`;
2. reject invalid UTF-8, duplicate JSON keys, non-finite JSON numbers, an unsafe generation ID, or a pointer that fails the vendored Schema;
3. read only `generations/<generationId>/manifest.json`;
4. verify the raw manifest SHA-256 against `current.json`;
5. validate the manifest Schema, exact generation identity, `ready` state, and artifact/hash inventory;
6. if `trending/explosion.json` is not published, return a valid `not_ready` product state without looking at another generation;
7. otherwise verify the Explosion Artifact hash and Schema and require its `generationId` to match;
8. stable-read every source capture copy referenced by that artifact, verify both manifest and provenance hashes, validate the capture Schema, recompute its canonical payload digest, and bind capture identity, time and coverage state;
9. validate cross-artifact invariants: non-overlapping repository IDs, contiguous ranks, unchanged fact ordering, coverage counts, and observation-window/source timestamps;
10. project the verified subset into the TopicEye DTO.

Stable reads open a regular file with no-follow where the platform supports it, compare path and open-file identities, read a bounded full snapshot twice, and require identical bytes and metadata. A same-length mutation, delete/recreate, symlink swap, invalid JSON, file replacement, or stale capture digest hidden behind a re-signed outer hash chain fails closed. The adapter never reads the raw observation ledger and never falls back to a flat file, fixture, previous generation, or database row.

An atomic A→B pointer switch therefore has two legal outcomes: a request already bound to A completes entirely from A, while the next request reads B. A response cannot combine revisions.

## API and product states

`GET /api/v1/rardar/explosion-board` is registered only in Rardar mode.

| Condition | HTTP | Contract |
| --- | ---: | --- |
| Adapter not configured | 503 | `rardar_intelligence_not_configured` |
| Configured root unavailable | 503 | `rardar_intelligence_unavailable` |
| Unsafe or invalid configuration | 503 | `rardar_intelligence_invalid_configuration` |
| Pointer invalid | 503 | `rardar_current_pointer_invalid` |
| Manifest, artifact, source copy, hash, Schema or cross-file invariant invalid | 503 | `rardar_generation_invalid` |
| Healthy generation without Explosion Artifact | 200 | `state=not_ready`, `reason=explosion_artifact_not_published` |
| Observation window warming | 200 | `state=warming_up` |
| Required 24-hour baseline missing | 200 | `state=baseline_missing` |
| Exact artifact ready | 200 | `state=ready` |
| TopicEye profile | 404 | Rardar product surface is disabled |

The ready DTO contains generation, publication/capture/window provenance, current coverage, exact and pending rankings, conflict count, and source-capture status. Exact rows preserve Rardar's `rank`, numeric GitHub repository ID, repository URL, total/baseline/24h Star facts, language/topics, and repository flags. Pending rows preserve the observed partial-window facts. It deliberately contains no summary, capability, score, AI explanation, or inferred cause.

## UI truth contract

The Rardar home page displays only the first five authoritative exact rows and at most three pending rows. Exact order is not recomputed in the frontend. It identifies the ranking as observed 24-hour Star growth, exposes coverage/update/generation context, and labels the absent subjective layer as “AI 项目解释尚未接入”.

Warming, missing-baseline, unpublished, unconfigured, and integrity-error states have separate copy. Warming and missing-baseline states suppress the exact board but continue to show up to three verified pending facts, so first-seen projects are not hidden while the 24-hour baseline is incomplete. No state is replaced with TopicEye content or a POC fixture.

## POC disposition

| POC element | Formal disposition |
| --- | --- |
| One request / one revision, explicit error codes, hash validation, fact-order preservation | `PROMOTE` |
| Safe reader, strict schemas, service/API shape, and fact UI | `ADAPT` to the real Rardar generation contract |
| A/B mock pointer, mock projects, AI runtime, Find Project Jobs, diagnostics, two tables and migration | `POC_ONLY` |
| Hard-coded fixture roots, fake summaries/capabilities/Stars, AI recomposition, database authority, repository-to-content mapping, old-fixture fallback | `REJECT` |

No POC commit or directory is merged wholesale, and TopicEye POC PR #1 remains independent.

## Vendored contracts and fixture provenance

The minimal schemas live under `backend/app/integrations/rardar/contracts/`. `provenance.json` records the Rardar repository, exact merge SHA, source paths, source SHA-256 values, and vendored SHA-256 values. CI validates local bytes and does not clone Rardar.

The two formal A/B fixtures were created in an isolated detached Rardar worktree at the exact merge SHA. The generator built fictitious observations, ran the official `derive_trending_explosion` path, and required Rardar Schema and Audit to be healthy with retained generations present. Each extracted current generation has 5 exact, 3 pending and 2 conflict facts. Only the minimal files needed by this adapter were copied; no Production data, token, D1 state, or user repository was used.

## Persistence and operational boundary

The adapter imports no TopicEye model or repository and opens no database session. GET requests perform zero PostgreSQL writes, create zero tables, and do not change normalized database exports. It also writes nothing to Rardar, never changes `current.json`, and holds no Rardar data lock.

There is no long-lived Adapter Worker. Parsing is request-scoped and bounded by the Rardar contracts (500 exact, 500 pending, 500 conflicts). Resource measurements in the implementation record are local snapshots, not capacity promises.

## Rollback

1. disable Rardar traffic or set `RARDAR_PRODUCT_MODE=false`;
2. stop the TopicEye backend/frontend process using the adapter;
3. revert the adapter application commit and reinstall exact dependencies;
4. restart TopicEye and verify its default product surface and Admin;
5. leave Rardar `data/`, generations and pointer unchanged.

No database downgrade, fixture restoration, Rardar rollback, or destructive cleanup is required.
