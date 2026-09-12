# RARDAR-INTRO-HISTORY-FIX-01

Baseline: `cde7ba04b43e4e781ea8441001977d8f292b345c` (TopicEye).

## Focused changes

- Preserve a validated Chinese introduction with bound source evidence even
  when the complete Profile fails. Mark it partial, keep complete validation,
  retain previous good content on failure, and continue bounded material work.
- Reuse translation stages by actual material and route identity rather than
  board generation. Retain compatible legacy stage-cache reads.
- Persist optional Description and cumulative Star in the existing metadata
  cache (v2, compatible with v1). History chooses the latest valid value, not
  the maximum, and no longer derives or displays growth. Today is unchanged.
- Keep complete cards, evidence, insight and Find links. No new scheduler,
  model route, ledger or historical-growth collection job is introduced.

## Actual diagnosis and manual repair

The saved current snapshot had 35 Today projects and 132 historical projects.
All 25 Today introduction gaps lacked a saved README/translation and had no
recorded Profile attempt: they were unprocessed, not 25 observed model failures.
Among historical gaps, two recorded translation failures and one incompatible
Profile digest were distinguished from missing material; invalid cached material
was not promoted. Full Profile publication also discarded an otherwise valid
introduction, which this change addresses separately.

Using the existing application entry and original daily budget identity:

| Project | Before | Result | New Provider requests |
|---|---|---|---:|
| google/artemis | English Description, no Chinese material | Complete saved Profile | 1 |
| nvlabs/sol-pi | No saved Description or Chinese material | Valid README-bound Chinese introduction; full Profile still invalid/partial | 1 |
| google/artemis repeated | Healthy saved result | Reused with all outbound HTTP forbidden | 0 |

These are manual repairs in isolated candidate data, not a natural 09:00 run.
The original 2026-09-13 ledger read 2/100 after processing (10 reserved for
interaction); no test ledger was created. Candidate Today Chinese introductions
rose 10→12, complete Profiles 10→11; history 48→50 and 46→47 respectively.
Board membership, ranks, source periods and generation were not refreshed.
The partial SoL-Pi introduction only identifies the extension; its broader
capabilities remain unfinished, not silently filled in.

## Verification and delivery status

Focused backend regressions, changed-file lint, frontend unit tests/type checks
and the isolated production build passed. Real API/browser acceptance and
exact-head CI are tracked in the PR; a build or API check is not visual proof.
Browser inventory initially failed with `nodeRepl.fetch request failed`, but
direct connection to the built-in browser worked; real candidate-page acceptance
continues there. Local diagnostic materials remain outside Git under the existing
audit-export directory. The original 09:00/11:00 schedule, budget and Runtime
remain unchanged until the reviewed deployment is verified.
