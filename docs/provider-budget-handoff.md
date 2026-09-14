# Offline daily provider budget handoff

`python -m app.services.llm.provider_budget_handoff` supports `export` and
`import` from the backend directory. This operator tool never accesses a
provider, database or credentials. Do not put API keys in its arguments.
Use an isolated checkout with no `.env` and set
`DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:1/test` in its process
environment: the existing package initializer validates settings, although this
tool does not open a database connection. Never run this command from a live
runtime directory containing credential configuration.

Export arguments: `--root <read-only-copy-or-source> --source-root <original-registered-root>
--account-ref <independently-verified-nonsecret-account-reference> --bundle <new-file>`.
It checks every dated directory with two stable reads; it does not create source
locks. A running source export is preparation only, never the final cutover source.
The root manifest covers all dates. Raw event/snapshot/registration bytes and their
SHA-256 values are preserved. Windows registration paths are evidence strings;
no Windows directory is forged on Linux. Maximum registered daily allowance is
100; lower historical caps remain lower. Existing runtime policy preserves the
interactive reserve of 10 and narrower operation limits; this tool changes none.

Import arguments: `--root <absent-canonical-target-root> --bundle <bundle>
--account-ref <same-verified-reference> --digest <export-digest>`.
The default is dry-run with zero target writes. `--apply` additionally requires
`--stopped-source-ref <operator-evidence-reference>`. Account references do not
prove account ownership; provider config IDs and credential presence are not
billing-account evidence. The operator must independently reconcile all writers.
Tool output explicitly reports `accountVerification=not_verified_by_tool`.
No merge, sum, maximum-count heuristic or cross-host fencing is implemented.
Divergent or unknown target state is rejected, not repaired.

Before apply stop all source consumption entries, settle/record in-flight work,
take a final export, and keep all target consumption disabled. Unfinished
reservations remain spent, including unknown upstream outcomes. Import preserves
the event chain and request IDs exactly, creates new path registrations, and writes
a separate root handoff receipt last. This is an explicit association to the old
registration, not a claim that the registration bytes did not change. Import
builds a private sibling staging directory, validates all dates and the receipt,
then atomically publishes the entire root without replacing an existing target
(Windows rename or Linux `renameat2(RENAME_NOREPLACE)`, with no unsafe fallback).
A failed partial import never exposes the canonical target and is retained for
forensics. Its final-path registrations also reject consumption from staging.
Target-parent ownership must prevent unrelated writers during import. Never clear
a partial or existing ledger to retry; review its evidence first. Unknown files
inside a dated directory are rejected, not silently omitted from the export.

Compute the target root using the existing runtime `daily_root()` identity rule
for the actual Linux data root and service account. Set the existing
`RARDAR_BUDGET_IDENTITY_DATA_DIR` to that real absolute data root: this existing
binding requires its derived budget root to exist, preventing a typo from silently
creating an independent allowance. Verify the receipt, all imported dates and
runtime configuration before enabling the server as the only consuming writer.
Do not activate an independently writable source with the same identity string.
New calendar days follow the existing Shanghai-day policy; old days are not reset.

Repeated import with the same receipt accepts only a target journal extending the
imported prefix and never overwrites it. Source bytes remain bundled for forensic
comparison. Ordinary local lock files are not transferred. This tool supplies
offline integrity checks, not authorization, distributed fencing, or permission
to spend. Final publication still needs the release's other gates.
