# Rardar public reading and explicit AI actions

Public visitors may read Today, the stable eight-project history, project facts,
saved public project materials and shared saved AI interpretations. Activity
remains a clear not-connected placeholder. Find's form is public; submitting it
and reading a user's saved Find runs require the existing application identity.
Shared AI generation is also an explicit authenticated action. Login returns to
the original page without executing that action. Unsent Find inputs can survive
that navigation in tab-local temporary storage; private results remain server
records, scoped to their original owner.

The existing password login/session is reused. Rardar does not expose public
registration, verification-code or OAuth signup flows in this phase. TopicEye's
independent mode retains its existing login and registration behavior. Management
and source refresh remain administrator operations even when no model is used.
The four retired product URLs retain their existing public paused explanation;
their data and execution APIs are not opened and their jobs are not resumed.

## Existing paths and minimal changes

| Existing path | Change | Evidence |
| --- | --- | --- |
| Rardar model POST routes and Find identity | Authenticate all retained model entry points; treat edge Basic as neither user identity nor CSRF proof; close the short auth transaction before model work | Actual ASGI authorization tests with inert business calls |
| Public product layout | Reuse lightweight AuthProvider consistently for lists/details; public form and explicit login CTA; no generation after login return | Real component tree tests and production-build browser fixtures |
| Shared saved insight GET | Remains public, read-only and independent of generation | Anonymous saved-result fixture and backend GET regressions |
| Fixed Rardar Nginx vhost | Method/path map removes Basic only for the specified reading and application-auth routes; unlisted/management paths keep the original protection | Static policy cases, then actual candidate nginx syntax and live anonymous checks |
| Production cookie-origin configuration | Append the actual `https://rardar.dokitool.com` to the existing CORS origin string; no wildcard or other env change | Runtime-reviewed exact before/after configuration and source-guard tests |

`deploy/nginx/rardar-public-edge-map.conf` and
`deploy/nginx/rardar-public-reading-site.conf` are the fixed Rardar inputs, not
changes to the generic TopicEye Nginx template. TLS, proxy destination, stripping
of edge Authorization, existing rate limits, headers and timeouts are preserved.
Registration, OAuth, unknown TopicEye APIs, metrics, dashboard and admin paths do
not become public simply because the main page does. Application authentication
still protects private Find reads and every model POST after edge Basic is off.

The two Nginx files, the one CORS field and their previous bytes must be bound to
the reviewed Runtime release, tested before reload and restored on failure. Do
not overwrite htpasswd, keys, credentials, budgets or unrelated vhosts. Deploy
the authenticated backend before opening the reading surface.

## Verification boundaries

Development uses temporary stores and explicit synthetic backend/browser inputs.
No Provider call, source refresh or paid production probe is needed for these
authorization checks. Anonymous rejection must happen before the business/model
function. Saved public content and private Find readback are tested separately.
Synthetic login exercises the real login UI with an HttpOnly fixture cookie; it
is not evidence of a real production login or new model output. Final production
anonymous and existing-account checks are recorded separately by Runtime and the
actual browser, without submitting a new Find or generating an interpretation.

Today growth >=200, historical daily eight, 09:00 main/11:00 conditional refresh,
daily 100 requests with reserve 10, paused News/Discover and all historical
results and ledgers remain unchanged. This task adds no account system, queue,
scheduler, automatic paid action or new allowance.
