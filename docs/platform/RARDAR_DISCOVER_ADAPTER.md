# Rardar Discover Adapter

## Purpose

TopicEye consumes Rardar's audited `TrendingDiscoverArtifact` v1, v2 and v3 as a
near-real-time project-discovery surface. Rardar remains the sole fact
producer. TopicEye validates and projects the artifact, builds evidence-backed
static project profiles during sync, and serves the result without recomputing
stage membership or order.

The vendored contract is pinned to `Brilliant666/rardar` merge
`ce3437ecc76765d5961af7a78d08962dce964d63`. Exact source and vendored hashes
are recorded in `backend/app/integrations/rardar/contracts/provenance.json`.
Runtime consumption never depends on a Rardar checkout.

## Product semantics

### Current runtime and approved evolution

The four-section contract below describes the currently implemented adapter and
Serving generation. The calibrated v3 product direction is documented in
[`RARDAR_DISCOVER_WORTH_SEEING_MODEL_V1.md`](../product/RARDAR_DISCOVER_WORTH_SEEING_MODEL_V1.md):
Discover will become an evidence-bound “worth seeing now” selection outside
Today Top 20, with no public numeric rank. Producer momentum remains an
immutable auxiliary Timeliness fact; it is excluded from the Value payload and
cannot make weak value strong. TopicEye must assess Scope, momentum-blind Value,
and Timeliness separately. A deterministic matrix owns the semantic decision,
fixed precedence owns Primary Reason, and peer context may affect only duplicate
packing. The original Internal Holdout is now revealed historical evidence. A
new, disjoint 24-project Fresh Holdout passed every frozen gate after the output
contract was reduced to a minimal alias-bound Schema. PR #26 is the docs-only
acceptance vehicle; after its exact reviewed revision merges, only a separate
Local/Shadow Selection Runtime implementation is permitted. Production
activation is not authorized. This docs-only decision does not change the
behavior below.

Discover means the most recent verified natural Observation, normally updated
every two hours. It is not a stream, a full-GitHub scan, or a second Today
ranking. The page preserves four producer-owned sections:

1. `just_discovered` — 刚刚发现;
2. `outside_today_momentum` — 榜外异动;
3. `rising` — 持续升温;
4. `near_validation` — 待日榜验证.

Within each section, Rardar's deterministic order is preserved. TopicEye does
not score, filter, refill, re-rank, or use AI to choose candidates. V2 binds
each published item to producer-issued signal facts and reason codes and binds
the artifact to its aggregate suppression summary. The safe reader validates
that proof but deliberately does not re-select unpublished candidates. Star
change is always paired with the actual observation window; no 24-hour
extrapolation is calculated or displayed.

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
captures, stage membership and deterministic order by full recomputation for
v1, or producer-issued signal facts, publish reasons, policy constants and
suppression invariants for v2/v3;
- for v3, the Today exact set, published rank 1–20 numeric-ID set and digest,
  eligibility classes, recent/prior comparable windows, acceleration, relative
  growth, positive intervals, reasons, suppression and all four stage orders;
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

Serving v2 also adds exactly one static product category to every selected
project. The deterministic classifier first uses the canonical profile
(product forms, use cases, delivery form, positioning and sourced
capabilities), then GitHub topics/language, then the explicit `other` fallback.
It records `category`, `categorySourceMode` and `categoryEvidenceRefs`. Category
never changes producer selection, stage or order and never requires a page-time
GitHub or model call.

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

For v3, a Discover generation contains bounded source descriptors rather than
physical copies of every Observation capture. Sync fetches the referenced
canonical files from `observations/trending/v1/captures/`, verifies every
declared file and payload digest, and stores each immutable source once. A
descriptor conflict fails the whole activation before pointer replacement.

## API and pages

The following routes are registered only when `RARDAR_PRODUCT_MODE=true`:

- `GET /api/v1/rardar/discover`;
- `GET /api/v1/rardar/discover/projects/<numeric-id>?generationId=<discover-id>`;
- `POST /api/v1/rardar/discover/projects/<numeric-id>/insight`.

The collection API reports `ready`, `empty`, `stale`, `not_configured`, or
`invalid`, plus cadence, latest capture, next expected update, stage counts,
coverage and a bounded conflict summary. V3 additionally exposes the fixed
`todayPublishedTopCount` and an eligibility summary separating Observation
candidates, Today exact facts, Today published projects, excluded published
projects, exact-outside-published evaluation, pre-exact evaluation, invalid,
published and suppressed projects. A normal page request reads only the static
Discover Serving generation. It performs zero raw Discover reads, zero GitHub
calls, zero model calls and zero PostgreSQL fact writes.

`/discover` renders four honest sections and category-aware empty states. The
fixed filters are 全部, AI 与 Agent, 开发工具, 数据与基础设施, 生产力,
视频与内容 and 其他. Filtering operates only on the already-published static
cards, preserves producer order and stores its state in `?category=` for
refresh and browser history. The full card is the internal pointer/keyboard
target; the title remains a normal internal link and the GitHub link remains an
independent external link. Internal project links use
`/project/github/<numeric-id>?discoverGeneration=<discover-generation>`. The
existing detail component is reused, but its fact block shows Discover stage,
eligibility class, first/latest observation, actual window and delta,
capture/positive-interval continuity, latest interval, next Observation, next
Today settlement and the deterministic reason it has not entered Today. An
`outside_today_momentum` detail also shows the factual Today exact rank and 24h
delta, published Top 20 boundary, recent/prior equal windows and acceleration.
It does not imply a predicted rank or extrapolated 24h value. AI deep insight
remains an explicit user action through
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
