# Rardar Discover Adapter

## Purpose

TopicEye consumes Rardar's audited `TrendingDiscoverArtifact v1` as a
near-real-time project-discovery surface. Rardar remains the sole fact
producer. TopicEye validates and projects the artifact, builds evidence-backed
static project profiles during sync, and serves the result without recomputing
stage membership or order.

The vendored contract is pinned to `Brilliant666/rardar` merge
`b99a8b88a9b46b830f5170824a7c90ead41cc51a`. Exact source and vendored hashes
are recorded in `backend/app/integrations/rardar/contracts/provenance.json`.
Runtime consumption never depends on a Rardar checkout.

## Product semantics

Discover means the most recent verified natural Observation, normally updated
every two hours. It is not a stream, a full-GitHub scan, or a second Today
ranking. The page preserves three producer-owned sections:

1. `just_discovered` — 刚刚发现;
2. `rising` — 持续升温;
3. `near_validation` — 接近验证.

Within each section, Rardar's deterministic order is preserved. TopicEye does
not score, filter, refill, re-rank, or use AI to choose candidates. Star change
is always paired with the actual observation window; no 24-hour extrapolation
is calculated or displayed.

## Safe raw adapter

`DiscoverArtifactAdapter` binds one request to one immutable Discover
generation and verifies:

- the backend-only `RARDAR_INTELLIGENCE_DATA_DIR` root and no-follow path
  containment;
- current pointer, generation ID, ready manifest and exact inventory;
- manifest, artifact, Today source and capture-copy SHA-256 values;
- strict JSON, duplicate-key/non-finite rejection, vendored JSON Schemas and
  payload digests;
- source capture identity, cadence, order, coverage and payload digest;
- Today exact exclusion by numeric GitHub repository ID;
- numeric identity continuity, conflicts, actual windows, deltas, consecutive
  captures, stage membership and deterministic order by full recomputation;
- symlink, junction, reparse point, path escape, temporary file and unstable
  read rejection.

Integrity failures use stable bounded errors and never fall back to fixtures or
an unverified generation. A complete but late Serving remains readable and is
explicitly marked `stale`.

## Static Discover Serving

Raw Discover data is read only by sync or rebuild. The publication step takes
the first ten projects from each producer section without cross-filling and
reuses the existing official-profile/evidence contract. Every selected project
must have a publishable Chinese identity, distinct evidence-backed positioning,
at least one sourced capability and valid evidence references. One failure
blocks the entire candidate; the previous healthy Serving remains active.

The independent store is:

```text
RARDAR_INTELLIGENCE_DATA_DIR/
├─ artifacts/trending/discover/v1/       # verified raw mirror
├─ discover-sync/generations/             # bounded sync metadata
├─ discover-profile-cache/                # reusable GitHub/LLM profile cache
└─ discover-serving/
   ├─ current.json
   ├─ sources/<discoverGenerationId>.json
   └─ generations/<servingGenerationId>/
      ├─ manifest.json
      ├─ discover.json
      ├─ projects/<githubRepositoryId>.json
      └─ evidence/<githubRepositoryId>.json
```

Generations are immutable, hash-bound and atomically activated. A repeated
sync of the same source/profile revision is a no-op. Today and Discover have
separate raw, metadata and Serving pointers; failure in one path cannot roll
back or overwrite the other.

## API and pages

The following routes are registered only when `RARDAR_PRODUCT_MODE=true`:

- `GET /api/v1/rardar/discover`;
- `GET /api/v1/rardar/discover/projects/<numeric-id>?generationId=<discover-id>`;
- `POST /api/v1/rardar/discover/projects/<numeric-id>/insight`.

The collection API reports `ready`, `empty`, `stale`, `not_configured`, or
`invalid`, plus cadence, latest capture, next expected update, stage counts,
coverage and a bounded conflict summary. A normal page request reads only the
static Discover Serving generation. It performs zero raw Discover reads, zero
GitHub calls, zero model calls and zero PostgreSQL fact writes.

`/discover` renders three honest sections and empty states. Internal project
links use
`/project/github/<numeric-id>?discoverGeneration=<discover-generation>`. The
existing detail component is reused, but its fact block shows Discover stage,
first/latest observation, actual window and delta rather than Today rank or a
fictional baseline. AI deep insight remains an explicit user action through
TopicEye's existing `routing_group=rardar` control plane. Find Project receives
only the canonical public GitHub URL.

Default TopicEye mode does not register these APIs and does not read the Rardar
filesystem.

## Operations and rollback

`scripts/rardar-local.ps1 sync-data` runs Today sync first and Discover sync
second, each with independent staging and pointer rollback. An isolated local
source can be selected for acceptance with
`RARDAR_DISCOVER_SYNC_SOURCE_DIR`; this variable is backend/operator-only and
is not exposed to the browser. `rebuild-serving` rebuilds Discover only when a
raw Discover pointer exists.

Rollback is pointer-based: keep the previous immutable Discover Serving and
raw generation, stop the sync writer, restore the previous validated pointers,
then re-run the adapter and Serving validation. No database migration or data
rewrite is required. Today is not part of this rollback.

Production Discover publication and deployment are deliberately outside this
contract. They require the separate
`RARDAR-DISCOVER-RUNTIME-ACTIVATION-01` operation.
