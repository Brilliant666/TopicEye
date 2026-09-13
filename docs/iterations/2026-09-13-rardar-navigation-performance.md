# Rardar navigation read-path performance

Scope: Today and daily historical review reads only. No source refresh, model
request, scheduler, budget, ranking, or historical batch mutation is introduced.

The local production baseline at `b60c0c5` used saved real boards and the existing
ordered daily eight. Ten samples per direction on desktop and mobile viewports
showed roughly 0.76 seconds returning to Today and 0.32 seconds entering history.
Navigation used RSC, not a document reload. `no-store` did not impose a fixed
15-second wait. Backend profiling found broad material reads and repeated history
aggregation: Today expanded 129 material records, including 80 retained details;
history projected metadata for 146 repositories before selecting eight.

Changes:

- Resolve only qualified Today repositories and published historical identities.
  Empty scopes remain empty; legacy missing numeric identities use a reusable
  validated lookup rather than widening each material read.
- Reuse validated public fact/material projections in a bounded process-local
  cache (96 entries, shared 20-second epoch). Nested reuse does not add TTLs.
  Known directory changes invalidate early; in-place/legacy changes are rechecked
  within 20 seconds. Source freshness, latest checks, metadata and attempt states
  remain live. There is no Next fetch cache or new disk fact store.
- Send only card narrative fields on list responses. Full profiles and evidence
  remain available from the same detail path; card render equality is tested.
- Run the four disk-backed public read services off the async request loop.

First access/epoch rebuild can still scan retained history and legacy identities;
that cost is reported separately, not claimed to be constant in history size.
Invalid builds are not cached as successful data. Public cache keys contain no
authentication or private Find response.

Validation: focused scope, cache invalidation, single-flight, identity, partial
introduction, daily batch and full-detail regressions; frontend render equality,
types and changed-file lint; real production-browser and direct HTTP samples in
the local `audit-exports/nav-perf-fix-20260913` directory. Final CI/deployment and
after measurements are recorded in the PR and local report.

Next.js 16.3.4's bundled navigation/Link documentation was checked. Existing Link
navigation and `no-store` remain; no all-project detail prefetch was added.
