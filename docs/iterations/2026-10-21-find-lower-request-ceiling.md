# Find acceptance: lower per-run request ceiling

The authenticated `POST /api/v1/rardar/find-runs` accepts an optional
`X-Find-Request-Limit` nonnegative integer. The existing service persists the
minimum of that ceiling, server configuration and available daily allowance
before execution. Omitting the header retains normal product behavior.

This is a reduction, not another budget pool or a permanent three-call product
limit. Existing outgoing-request reservation still covers planning, comparison
and retries. Reusing an idempotency key cannot increase its saved ceiling. If an
existing run exceeds a newly requested ceiling, creation returns a conflict;
it does not silently return an unsafe run or modify historical consumption.
Check the returned `requestLimit` before the separate execute operation.

For this release acceptance only, prior consumption is 2 of 5; the next run
must request at most 3 and also obey the current daily balance. No acceptance
model request is made by these tests. Existing private results stay private.

Validation: API regression failed before the fix (header ignored); 75 focused
API/persistence/dispatch/budget tests passed afterward with simulated transport
and isolated temporary databases. Browser, deployment and real generation are
separate acceptance gates, not established by these tests. No migration,
shared model configuration, credentials or scheduler changes.
