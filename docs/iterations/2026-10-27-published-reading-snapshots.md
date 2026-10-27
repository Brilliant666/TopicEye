# Rardar: publish reading products before serving them

The retained PR56/PR91 improvements reduced scoped reads and lock contention,
but their process-local 20-second cache still assembled public cards on a cold
request. The public Today/history path now separates publication from reading.

- Existing source, metadata, fixed-history, material and repair writes publish
  validated reading products. Startup can bootstrap saved data without fetching
  sources, initializing a history batch or calling a Provider. No new schedule.
- Each view atomically advances its own small pointer. Content-addressed list
  products refer to shared immutable project bodies; list GET never loads full
  evidence. Failure retains the old view. Missing raw inputs at restart cannot
  replace a real published board with an uninitialized empty board.
  Manual publication records reuse the existing day receipt and writer lock,
  so a failed local publication can use the existing conditional opportunity.
- Next reads the small pointer without caching it, then caches the selected
  immutable public URL. A new material/Star/status revision is visible without
  rebuilding the frontend. Lists and details pin the same reading revision,
  including when the fact generation is unchanged. Old unversioned archive
  links retain their existing strict compatibility reader.
- Normal GET does not rebuild, lock or write products. Account state, private
  Find runs, shared insight generation and administrator operations are not
  included in this public cache. Existing edge authentication rules are unchanged;
  Next fetches the new endpoints through its configured internal backend URL.
- `python -m scripts.refresh_rardar_boards --publish-reading-only` publishes only
  saved local data. It cannot be combined with source/metadata/material modes.
  It neither creates a daily budget nor performs source or model requests.

Saved production snapshot replay (2026-10-27): Today29/history8, all members and
existing content equal before/after, excluding the added reading revision.
Three-sample median service cold reads: Today2123.639→24.294ms;
history848.187→15.213ms. Cold clears Python caches, not the OS file cache. New
list cold reads open two product files; warm reads open one pointer. All37
detail bindings were checked. This is controlled offline replay, not live P95.
Same-input rebuilding still validates raw inputs; it reused all products and
left pointer bytes unchanged. No claim that write-side assembly is free.

Tests cover pointer failure, corrupt artifacts, independent views, missing
materials, cross-process reads, same-generation changes, exact old details,
daily/CLI/repair hooks, and protected-operation separation. Production-build
browser tests use explicitly synthetic HTTP fixtures for repeatable publication
changes and authorization. Actual saved-data and deployed-browser acceptance
must be reported separately; CI alone is not deployment or natural-day evidence.

Today >=200, fixed history8, source/rank/time semantics,09:00/conditional11:00,
daily100/reserve10, paused News/Discover and persisted Find results are unchanged.
The task makes zero new app Provider requests and does not manually refresh sources.
