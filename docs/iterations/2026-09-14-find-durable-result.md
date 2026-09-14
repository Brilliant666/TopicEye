# RARDAR-FIND-DURABLE-RESULT-01

Baseline: TopicEye `fb8c06a5773014afe6f6b8616364b2281f280228`.
Development branch: `codex/rardar-find-durable-result`.

Private PostgreSQL runs now own request identity, idempotency, short-transaction
execution claims, evidence/result snapshots, bounded outbound reservations and
terminal states. Existing Find recall and evidence comparison remain unchanged.
The browser saves only temporary keys/IDs and reads user-scoped server results.
No new queue, account system, Redis, scheduler or budget ledger is introduced.

## Verification

- Isolated disposable SQLite persistence/concurrency tests; mocked transport and
  API authentication tests, no real Provider or source calls.
- Separate `rardar_development` PostgreSQL: pre-migration dump retained outside
  Git; additive upgrade → downgrade to `c003bd551911` → upgrade passed. The
  Windows Alembic config was read explicitly as UTF-8; no application code or
  production configuration changed to work around the host encoding.
- Frontend unit/type/changed-file lint verified; production-browser fixture
  coverage runs in CI and is not evidence of a real Provider result.
- Server remains DEPLOYED on its previously accepted artifact until incremental
  release gates pass. This PR does not import local data or alter old ledgers.

## Release acceptance boundaries

The original additional five-request acceptance allowance is shared with prior
release work, not renewed by this PR. Runtime's read-only Sep14 22:39 Shanghai
sample confirmed prior acceptance use 0, daily100/reserve10 unchanged. Recheck
before the single real Find and bind its persisted ceiling to the then-remaining
authorization and daily availability. No request has been made by this development
work. Private queries/results and credentials must not enter this document/PR.

Real desktop/mobile review, normal app login, real generation/readback and
natural daily execution are separate gates. Browser provider discovery currently
fails (`nodeRepl.fetch request failed`); Chrome was not reset. Application login
requires the owner's existing credential/session, not edge Basic Auth. Natural
Sep15 09:00/11:00 observation keeps the existing one-shot read plan; no new timer
or artificial catch-up is created.
