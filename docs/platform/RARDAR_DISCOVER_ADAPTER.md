# Rardar Discover Adapter

## Purpose

TopicEye consumes Rardar's audited facts through two independent local paths.
The retained legacy momentum projection reads `TrendingDiscoverArtifact` v1,
v2 and v3 for diagnostics and Shadow comparison. The active local `/discover`
product reads a separately validated, hash-bound mirror of Observation captures
and the authoritative Today artifact, then builds an evidence-bound, unranked
“worth seeing now” Selection outside Today Top 20. Production Discover is not a
prerequisite. Rardar remains the sole fact producer; TopicEye owns Selection
semantics and never rewrites an Observation, Today fact, Star value or
eligibility decision.

The vendored contract is pinned to `Brilliant666/rardar` main
`34556a3ce4765acdc6a91f6fc895846aa33ee5f2`. Exact source and vendored hashes
are recorded in `backend/app/integrations/rardar/contracts/provenance.json`.
Runtime consumption never depends on a Rardar checkout.

## Product semantics

### Current local Shadow runtime

The calibrated v3 product contract is documented in
[`RARDAR_DISCOVER_WORTH_SEEING_MODEL_V1.md`](../product/RARDAR_DISCOVER_WORTH_SEEING_MODEL_V1.md):
Discover is an evidence-bound “worth seeing now” selection outside Today Top
20, with no public numeric rank. Producer momentum remains an
immutable auxiliary Timeliness fact; it is excluded from the Value payload and
cannot make weak value strong. TopicEye must assess Scope, momentum-blind Value,
and Timeliness separately. A deterministic matrix owns the semantic decision,
fixed precedence owns Primary Reason, and peer context may affect only duplicate
packing. The Scope/Value Gate uses `prompt_json` plus strict local parsing,
Schema validation and repository-bound Evidence Aliases. Model output cannot
own the final decision, primary reason, public order or publication fallback.
Production activation remains unauthorized.

### Retained legacy momentum projection

The four-section contract below describes the retained compatibility adapter
and Serving generation. It is no longer the data source for the local
`/discover` page.

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

## Worth-seeing Selection and static Serving

The Selection source synchronizer verifies a repository-external bundle with a
26–72 hour Observation inventory, the authoritative Today generation and every
source hash before atomically activating its own pointer. The Selection builder
loads that validated source and forms the complete latest-capture universe. It
excludes only Today's published Top 20 numeric IDs and invalid, archived,
disabled, forked or incomplete identities; exact rank 21+ remains eligible. Six
deterministic channels recall 30–60 candidates. Momentum-only recall is capped
at 40%, and no aggregate score exists.

Each recalled project receives a bounded evidence package from Profile Cache
v2 and, only when missing, GitHub README/tree/release endpoints. Cache identity
is based on the static evidence content and relevant derivation/model versions,
not Observation generation, Star, rank or momentum. Equivalent healthy content
is rebound to the current evidence aliases and Selection provenance without a
GitHub or profile-model call. A true miss uses the established profile builder;
every model call remains inside the artifact's shared 120-call limit.
Repository content is untrusted text, never executable input. Value evidence
uses `E##`, timeliness uses `T##`, and peer packing context uses `P##`; aliases
are verified against the same numeric repository ID. The Value payload is
scanned after serialization and rejects momentum/rank/Observation language.
Format-only failures get at most one retry; all structural or evidence failures
become `UNCERTAIN`, never Star fallback.

The immutable store is repository-external:

```text
RARDAR_INTELLIGENCE_DATA_DIR/
└─ discover-worth-seeing/
   ├─ current.json
   ├─ latest-attempt.json
   └─ generations/<selectionGenerationId>/
      ├─ manifest.json
      ├─ raw/selection.json
      ├─ serving/selection.json
      └─ serving/projects/<githubRepositoryId>.json
```

The generation identity binds source facts, Profile revision and projection
binding sets, assessment output, failure resolution, every policy version and a
secret-free model-route fingerprint. Publication validates the raw and public
projection, hashes every file and checks the exact inventory. A `ready` or
fully assessed `empty` generation atomically updates both `latest-attempt` and
`current`; a `degraded` generation updates only `latest-attempt`, preserving the
last healthy current. Retryable failures live in a separate append-only attempt
ledger with bounded backoff and cannot replace a healthy Profile Store entry.
Only an unchanged healthy input is a durable no-op. Rollback validates a
retained healthy generation before reactivating `current`; it never falls back
to legacy momentum or modifies Today.

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

- `GET /api/v1/rardar/discover/selection`;
- `GET /api/v1/rardar/discover/selection/projects/<numeric-id>?selectionGeneration=<selection-id>`;
- `GET /api/v1/rardar/discover`;
- `GET /api/v1/rardar/discover/projects/<numeric-id>?generationId=<discover-id>`;
- `POST /api/v1/rardar/discover/projects/<numeric-id>/insight`.

The collection API reports `ready`, fully assessed `empty`, `degraded`,
`stale`, `not_configured`, or `invalid`, plus current/latest-attempt identities,
profile and assessment coverage, safe failure codes and a bounded retry time.
When a degraded attempt has no healthy predecessor, items are empty without
claiming that no worthwhile projects exist; otherwise the prior healthy items
remain visible. V3 additionally exposes the fixed
`todayPublishedTopCount` and an eligibility summary separating Observation
candidates, Today exact facts, Today published projects, excluded published
projects, exact-outside-published evaluation, pre-exact evaluation, invalid,
published and suppressed projects. A normal page request reads only the static
Discover Serving generation. It performs zero raw Discover reads, zero GitHub
calls, zero model calls and zero PostgreSQL fact writes.

`/discover` reads the Selection route only and renders one unranked stream. The
fixed category filters are 全部, AI 与 Agent, 开发工具, 数据与基础设施,
生产力, 视频与内容 and 其他; fixed reason filters are 全部理由, 可直接复用,
解决具体问题, 独特实现 and 参考与学习. Both are URL state and only filter the
already packed order. The whole card is a pointer and Enter/Space target; the
GitHub link remains independent. Internal links bind the numeric ID and
Selection generation. The detail reuses the canonical project profile and
adds only Selection value, timeliness, evidence and provenance. Empty is a
valid 200 response; missing, corrupt or stale projections are explicit and
never fall back to the legacy momentum stream.

Default TopicEye mode does not register these APIs and does not read the Rardar
filesystem.

## Operations and rollback

`scripts/rardar-local.ps1 sync-data` runs Today sync first and Discover sync
second, each with independent staging and pointer rollback. An isolated local
source can be selected for acceptance with
`RARDAR_DISCOVER_SYNC_SOURCE_DIR`; this variable is backend/operator-only and
is not exposed to the browser. `rebuild-serving` rebuilds Discover only when a
raw Discover pointer exists.

`build-selection` (and its explicit `rebuild-selection` alias) creates and
activates a local Shadow Selection. `selection-status` exposes source,
generation, counts, failures and the next action. `selection-rollback` requires
an explicit retained generation ID. These commands reuse the existing
`routing_group=rardar`; they do not change provider, model, API base or key.

Rollback is pointer-based: keep the previous immutable Discover Serving and
raw generation, stop the sync writer, restore the previous validated pointers,
then re-run the adapter and Serving validation. No database migration or data
rewrite is required. Today is not part of this rollback.

Production Discover publication and deployment are deliberately outside this
contract. They require the separate
`RARDAR-DISCOVER-RUNTIME-ACTIVATION-01` operation.

## Bounded local cohort review (2026-09-04)

`RARDAR-DISCOVER-SHADOW-CONVERGENCE-01` introduces a separate, opt-in local
review surface. It does not relax full Selection publication: the frozen source
still has 48 recalled projects, 41 healthy profiles and 7 unresolved profiles.
Full Selection stays `degraded`; `productionReady` is always false. A completed
16-project cohort can independently be `shadowReviewState=ready` or `empty`
and `reviewable=true`. Zero selected projects is a legitimate cohort result,
not a claim about all eligible repositories. An incomplete or invalid cohort
is not reviewable.

The cohort is selected without AI or named-repository exceptions. Its strata
are six non-momentum value candidates, four high-momentum candidates, three
new/change candidates and three mature low-momentum candidates. Scarce strata
are allocated first, category/product-form coverage breaks ties, and numeric
repository ID is the final tie-break. The source/cohort manifests bind profile
revisions, complete cache identities, release evidence, recall membership and
the unresolved attempt history. They are immutable within a run. Missing
strata are explicitly recorded; unhealthy profiles and a replacement 17th
candidate are forbidden.

### Execution budget, not a per-build counter

The prior recovery's 383 distinct Provider request IDs were an execution-control
failure: the in-memory 120-call build counter did not bound retries, failover
and repeated processes as one task. Those historical calls are not reassigned
to the new authorization. This task has one new **40-attempt total**, shared
across negative controls, gate, change, copy, retries and exact-head reruns.

`ProviderBudgetLedger v1` lives outside Git. An append-only hash-chained journal
is authoritative; the JSON summary is replaced atomically. Each actual
`acompletion` dispatch first reserves budget under an OS file lock. Failed
calls and interrupted reservations are never refunded. A second process uses
the same journal and cannot receive another 40 calls. A separate execution
lock enforces concurrency one. LiteLLM's internal retries are disabled for
guarded calls so every upstream execution is visible. Cache hits append a
non-consuming receipt. Budget failures do not poison the provider circuit.

Selection calls require all three matching settings:

```text
RARDAR_LLM_RUN_ID=<one operator-created run>
RARDAR_LLM_BUDGET_PATH=<absolute external path>/provider-budget.json
RARDAR_LLM_BUDGET_LIMIT=40
```

Initialization is a separate explicit operator command and cannot reset an
existing registration or silently mint another run. Run progress receipts bind
the source, cohort, accepted contracts and route fingerprint. A crashed stage
does not repeat an unconfirmed initial call; completed validated results are
reused without Provider execution. Raw responses, prompts, keys and exception
text are not written into budget receipts or artifacts. Profile-model scenes
are forbidden when this task's budget is attached.

### Local commands and serving isolation

After code tests and exact-head CI, use the following explicit steps from
`backend/`, with absolute repository-external mirror and run paths:

```text
python -m scripts.build_rardar_shadow_review freeze --mirror <mirror> --run-dir <run> --run-id <id>
python -m scripts.build_rardar_shadow_review initialize-budget --mirror <mirror> --run-dir <run> --run-id <id>
python -m scripts.build_rardar_shadow_review run --mirror <mirror> --run-dir <run> --run-id <id>
python -m scripts.build_rardar_shadow_review install --mirror <mirror> --run-dir <run> --run-id <id>
```

The runner never fetches GitHub, builds profiles or synchronizes Production.
Six existing fixed controls precede 16 gate judgments; at most six cached
change assessments and six selected copy jobs follow. Scope/Value and copy
prompts, response schemas, decision matrix and primary-reason precedence are
unchanged; the narrowly authorized change-binding correction is described below.
Copy failure preserves membership and canonical identity/positioning/reason;
missing generated copy is hidden, never replaced with a seventh project.

`discover-shadow-review/current.json` is independent of full Selection,
Today, source and profile pointers. Immutable generations contain the audited
review artifact, compact serving response and bound detail contexts. Install
validates before atomic pointer replacement; `rollback_shadow` validates a
retained shadow generation before reactivation. No database migration is used.

Only `RARDAR_LOCAL_SHADOW_REVIEW=true` **and a non-production application
environment** enable this reader. Production ignores the flag. Request-time
reads verify the bounded immutable inventory and static projections; they do
not rebuild facts/profiles, traverse caches, access PostgreSQL, call providers
or write budget events. Invalid shadow data fails closed, without falling back
to a momentum list or presenting an old full Selection as the cohort. Switching
the flag off restores the unchanged full Selection reader.

The page keeps category/reason filters, URL history, card navigation, GitHub
and Find Project actions, with no public rank. It displays the 16-item cohort,
full unresolved count and shared Provider budget distinctly. Merge still
requires exact-head real review, clean production-build browser acceptance,
zero evidence violations and CI. Future production activation retains the
full >=95% profile/assessment, new-sample and natural-runtime gates.

### Meaningful Change evidence-binding recovery

The six original change requests supplied release evidence under `T01`, but
the invocation did not explicitly bind assessment kind or explain that release
evidence cannot justify `meaningfulUpdate=yes`. All six receipts recorded
`wrong_assessment_evidence`. Rejected parsed fields were discarded, and the
response cache was process-memory-only; the exact returned alias combinations
are unavailable. The audit therefore identifies a confirmed invocation gap,
not proven model disobedience or proven cross-scene cache collision. Lost
responses must never be reconstructed. The original six-shape test fixtures
are counterexamples, not purported recovered Provider output.

`rardar-worth-seeing-change-v4` adds only explicit assessment/alias/type
constraints. The four-field response schema remains
`rardar-worth-seeing-change-schema-v3`; the `T##` namespace remains
`worth-seeing-evidence-alias-v1`. Cache identity
`rardar-meaningful-change-cache-v1` binds `assessmentKind=meaningful_change`,
its separate scene, repository ID, source revision, prompt/schema/alias/cache
versions, allowed-evidence-set and full evidence-package digests, and the
secret-free model-route identity. A missing or mismatched identity fails closed.
An E/P/long reference, another repository's T alias, wrong source type or
unsupported `yes` is rejected without remapping or fuzzy matching.

This explicit recovery continues the same frozen source, 16-project cohort,
run ID and journal from attempted **28/40**. It does not freeze, initialize,
repeat controls/gates, restore profiles or change the model route. Before any
new dispatch, it verifies the original artifact and ledger ancestry, all source
and profile identities, and every reused receipt. The interrupted original
Scope receipt remains terminal `UNCERTAIN` and remains charged. The original
incomplete artifact and receipts are never overwritten.

Only after the zero-call audit and exact-head gates, an operator may execute:

```text
python -m scripts.build_rardar_shadow_review resume-meaningful-change --mirror <frozen-source> --run-dir <same-run> --run-id <same-id>
python -m scripts.build_rardar_shadow_review install-resumed --mirror <isolated-http-mirror> --run-dir <same-run> --run-id <same-id>
```

The same three budget environment values remain mandatory. Each of the six
unrecoverable change stages can dispatch at most once; format, transport and
route failover cannot consume a second attempt. Copy has the same single-call
limit, only for the actual 0–6 Preview members. Total attempts cannot exceed 40.
Completed new receipts replay locally; a started-only receipt is terminal and
does not silently retry. The new receipts retain only the normalized four-field
Schema result plus bound context, not raw response text or prompts.

Recovery writes `stage-receipts-meaningful-change-evidence-v1` and
`shadow-review-artifact-change-v4.json`. The artifact identity binds the new
versions, aggregate assessment-cache digest and original artifact identity.
Artifact audit revalidates every accepted result against its exact evidence;
rejected responses are counted separately and are never accepted evidence.
An isolated failed change becomes terminal `UNCERTAIN`. The same failure in
four or more change stages blocks with
`BLOCKED_MEANINGFUL_CHANGE_EVIDENCE_BINDING` before Copy. Such a result cannot
be installed or used to authorize merge. Copy failure does not change Preview
membership. Successful replay/install makes no further Provider calls.

Rollback uses the retained, validated local Shadow pointer or disables the
local opt-in; it does not rewind the budget journal, alter Today/full Selection,
or erase failed artifacts. This recovery does not enable Production Discover.
