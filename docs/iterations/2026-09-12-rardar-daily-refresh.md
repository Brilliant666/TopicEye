# RARDAR-DAILY-REFRESH-01

Baseline: `c1809b86b14b734f1b88e0537a1acae548ddf445`, TopicEye formal local Runtime.
No cloud, database migration, Provider routing or daily-budget changes.

## Observed behavior and correction

The product-mode APScheduler registered `8-23:30`, and `run_daily_refocus`
called both sources on every continuation. September 12 logs and immutable
publications confirm those hourly executions, not a separate Windows task.
The replacement is one main slot and at most one conditional compensation per
Shanghai execution day, protected by persisted source receipts, round admissions
and the existing file/DB locks. Manual board sync shares receipts without model
work. Source failure preserves healthy content; publication retry reuses saved
source results; materials-only work does not fetch boards.

## Source evidence and time policy

Normal [Trendshift](https://trendshift.io/) calendar selection for September 11
returned 25 rows carrying the same UTC date, rank and growth. All 25 visible
positions/growth labels matched that response. The application adapter also
retrieved this dated result at `2026-09-12T05:50:27Z`, using the current public
component's named date action, not a guessed API or fixed deployment hash.
The dated result is an ended UTC day, not a promise of permanent finalization.
Exact upstream readiness delay and backend growth accounting remain unknown.

[GitHub Trending daily](https://github.com/trending?since=daily) exposes “stars
today”; this inspection found no authoritative exact timezone boundary or
supported date-selection contract. Its sourceDate therefore remains unknown.

Main is provisionally UTC day-end + 60 minutes: **01:00 UTC / 09:00 Shanghai**.
Compensation is +120 minutes: **03:00 UTC / 11:00 Shanghai**, only when saved
state identifies eligible unfinished work. Parameters are server-configurable
safety margins, not claimed observed source availability at those exact minutes.

| Shanghai execution day | Main UTC / Shanghai | Conditional UTC / Shanghai | Trendshift target UTC day |
|---|---|---|---|
| 2026-09-13 | 01:00 / 09:00 | 03:00 / 11:00 | 2026-09-12 |
| 2026-09-14 | 01:00 / 09:00 | 03:00 / 11:00 | 2026-09-13 |
| 2026-09-15 | 01:00 / 09:00 | 03:00 / 11:00 | 2026-09-14 |

The Sep 12 UTC source period is `[Sep 12 00:00Z, Sep 13 00:00Z)`, or
`[Sep 12 08:00, Sep 13 08:00)` Shanghai. Before readiness, the earlier due day
remains current. Source date, successful fetchedAt, source checkedAt, publishedAt
and actual Shanghai budget day remain distinct. Historical snapshots are not
relabelled or treated as current-source failures merely because they are old.

## Verification scope

Focused isolated regressions cover clock boundaries, host timezone independence,
main/compensation limits, source-specific retry, receipt integrity, cancellation
recovery, manual reuse, material slices, budget/reserve waits and unchanged
publication. Public-source date verification is real; fixed-response tests are
not production snapshots. Actual preview/formal browser and final CI evidence
are recorded in the PR and local task evidence, not inferred from unit tests.

Local rollback: retain the prior commit, matched frontend build and managed
configuration; use the existing stop/build/start entry and validated immutable
board publisher if content rollback is needed. Never restore old PID state or
roll back consumed budget. No database restart is required. Natural-day unattended
execution and calibration of the provisional source delay remain to be observed.
