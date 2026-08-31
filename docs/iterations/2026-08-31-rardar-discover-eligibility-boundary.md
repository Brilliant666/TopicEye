# Rardar Discover eligibility boundary correction

## Goal

Consume Rardar `TrendingDiscoverArtifact v3` without confusing the complete
Today exact-fact set with the product's published Top 20. TopicEye must expose
the producer-owned `outside_today_momentum` stage and its audited facts while
keeping Today, database state, model routing and Production unchanged.

## Producer evidence

Rardar merge `ce3437ecc76765d5961af7a78d08962dce964d63` established the
versioned boundary `todayPublishedTopCount = 20`. The corrected eligibility set
is the latest Observation candidates minus the published numeric repository
IDs and invalid candidates—not minus every repository with a complete 24-hour
fact.

The isolated historical replay requested 108 hours and found 74 continuous
hours across 38 derive points. The old boundary evaluated only 2 unique
projects and produced 15 non-empty points. The corrected policies evaluated
the full eligible set. The selected deterministic policy uses a recent 4-hour
window, absolute growth of at least 10 Star or relative growth of at least 1%,
at least two positive intervals, and recent growth greater than the prior
comparable window. It produced 1,681 publications across 178 unique projects,
16 later Today Top 20 promotions, and an 18-hour median lead. These figures are
replay evidence, not an AI score and not a promise that every runtime point is
non-empty.

The compact v3 fixture and production-shaped local derive prove the storage
boundary: one generation is 3,861,093 bytes, duplicate Observation source bytes
are zero, and the rough growth estimate is 46,333,116 bytes/day,
1,389,993,480 bytes/30 days and 4,169,980,440 bytes/90 days. Production
retention is deliberately unchanged.

## TopicEye implementation

- Vendored v3 current, manifest and artifact schemas are pinned to the Rardar
  merge, while v1/v2 remain readable.
- The adapter verifies the published Top 20 set digest, eligibility classes,
  canonical Observation sources, recent/prior windows, acceleration, reasons,
  suppression and producer order. Any mismatch fails closed.
- Sync preflights and installs canonical immutable sources before atomically
  activating v3; repeated sync is a no-op and Today pointers are not read or
  changed.
- Discover Serving v3 selects at most ten cards from each of four stages and
  carries the producer eligibility summary into the API.
- `/discover` renders 刚刚发现 → 榜外异动 → 持续升温 → 待日榜验证. The
  榜外异动 card emphasizes the recent actual window and exposes the prior
  comparable window, acceleration, Today exact context and continuity.
- Project detail reuses the canonical static profile and renders a
  deterministic explanation. No model participates in selection, ordering or
  explanation of the eligibility facts.

## Isolation and rollback

Today artifact, rank, Star, profiles, details, Serving pointer and UI are not
modified. There is no database migration, new table, model configuration
change, Production write or deployment. The static pages perform zero GitHub,
LLM, raw-artifact and database writes.

Rollback is limited to restoring the prior validated Discover raw and Serving
pointers. Canonical source files and immutable generations may remain retained;
Today does not participate in this rollback.

## Validation contract

Backend coverage includes v1/v2/v3, canonical-source hashes and path safety,
published-set boundaries, all four eligibility classes/stages, tamper cases,
sync idempotency and Today isolation. Frontend coverage includes the fourth
stage, exact rank greater than 20, recent/prior/acceleration facts, deterministic
detail, category URL state, whole-card/GitHub/keyboard navigation and honest
empty/fail-closed states. Process-level Playwright runs at 375, 768 and 1440
pixels with no overflow, React error overlay or hydration error.

Production Discover activation remains a separate explicitly authorized task.
