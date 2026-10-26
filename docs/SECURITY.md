# Application security review

Reviewed on 26 October 2026 for the CS3216 final project, Group 3. The baseline
was `dev` commit `e19ee96f1debb93ceb66a521b9700f5a41e68d1f`. This is a source
review and a staging test plan, not a penetration-test certificate. The changes
below are proposed in separate pull requests; check their merge and deployment
status before treating a finding as resolved.

## Trust boundaries

The React frontend holds a Supabase user session and sends bearer tokens to
FastAPI under `/api/v1`. `app/services/auth.py` verifies signature, expiry,
issuer and audience. `app/api/auth.py` maps the verified subject to a local user.
The API uses privileged server database and Storage connections, so ownership
checks in services and repositories remain essential even with database RLS.
Browser roles should not access the application's tables directly.

Uploaded photos receive user-scoped, non-overwriting upload capabilities. The
server downloads and validates the actual bytes before creating a media record,
removes image metadata, and checks ownership before returning image data or
signed URLs. Room access adds membership, readiness and expiry checks. Signed
URLs are temporary bearer capabilities and must not be logged or shared publicly.

Model calls use the shared AI runtime and router. Each invocation has a deadline
and a model-call budget; validation repair and transport failover share that
budget. Cached personal results are scoped to the learner. Langfuse is a separate
data destination and needs its own privacy controls. Stripe webhooks form another
boundary: their signature must be verified independently of user authentication.

## Findings and proposed fixes

| Priority | Finding in the baseline | Proposed change |
| --- | --- | --- |
| High | Any signed-in user can call `/payments/test-set-tier` to change their allowance. Hiding the page does not restrict the API. | Remove the route, frontend toolbox and API helper. |
| High | A missing Stripe signature selects an unsigned-JSON fallback, even when a webhook secret is configured. The configured path also calls an unsupported SDK surface. | Always require the secret and verify the raw body with `stripe.Webhook.construct_event` before processing. |
| High | Portal customer selection trusts an email address rather than an account binding. | Resolve customers through server-owned `user_id` metadata and reject an unlinked portal request. |
| High | Analytics sends recovery tokens in URL fragments and private invitation or OAuth codes in query strings. Contentsquare loads before the application can mask them. | Mask URLs before loading the tag and sanitize pageviews, GA configuration, action defaults and referrers. |
| High, deployment-dependent exposure | `user_surveys` and both onboarding placement tables lack the RLS and grants restrictions used elsewhere. `xp_events` has RLS but lacks explicit grant revocation. Actual browser access depends on deployed grants. | Add a reviewed migration and catalog tests for all mapped application tables. |
| High privacy risk | Langfuse context exit automatically records original exception messages and stack traces despite content capture being disabled. | Record a safe error class/code and close SDK contexts without passing application exceptions into the SDK. Verify exported OpenTelemetry data. |
| Medium | Public support and survey submissions have no application rate limit, and JSON parsing has no request-size cap. | Bound actual streamed body bytes before parsing; add bounded process-local limits for public submissions. |
| Medium | Checkout and portal return URLs accept arbitrary origins. | Require the configured frontend origin and reject credentials, fragments and malformed URLs. |
| Visibility gap | Router calls are spans, so their token usage is ignored by the SDK; the enclosing generation can misattribute failover usage. A blanket mask also removes diagnostic metadata. | Make each outbound model call a generation, avoid duplicate usage on feature wrappers, and retain reviewed diagnostic metadata. |

The review found existing ownership filters on sessions, tasks, journals,
vocabulary, photos and rooms, signed-token verification, image-byte validation,
parameterized database queries, and RLS/grant restrictions on most tables. These
controls need regression tests; their presence does not prove every path is safe.

## Staging checks for the team

Use an isolated Supabase project and Stripe test mode. Create accounts A and B
with separate photos, journals, language profiles and sessions. Record expected
status codes and database effects, not screenshots of tokens or personal data.

| Area | Check | Expected result |
| --- | --- | --- |
| Authentication | Omit a token; use an expired token, wrong issuer/audience, invalid signature, or disallowed anonymous identity. | Protected routes return 401 without reading or modifying learner data. |
| Ownership | As B, request A's session, task, latest attempt, journal, vocabulary, media metadata and media image by ID. Repeat on mutation routes. | 403/404 as appropriate; no content, signed URL, reward or state change. |
| Rooms | Try an unrelated account, expired invite, ended room and removed photo; retry a previously valid partner URL. | Access follows current membership and lifecycle. A previously issued Storage URL may remain valid until its expiry. |
| Uploads | Submit another user's storage key, a mismatched asset ID, non-image bytes, oversized data, a decompression bomb and an image with GPS/EXIF metadata. | Invalid uploads are rejected; accepted stored images contain no private metadata. |
| Billing | POST to the removed tier route. Send absent, invalid, stale and body-mismatched webhook signatures, then a valid Stripe test event. | Removed route is 404. Invalid events cannot change a tier. A valid event follows the intended subscription transition. |
| Billing identity | Request a portal with a matching email but no matching user metadata. Try a foreign return origin or a URL with userinfo. | No other customer's portal; unlinked customer is 409; unsafe return URL is 400. |
| Request limits | Send ordinary JSON over 1 MiB and support JSON over 15 MiB, including chunked requests with no trustworthy length. | 413 before JSON parsing, mail sending or database writes. |
| Submission abuse | Exceed five public support requests or ten surveys per address in ten minutes. Repeat with forged forwarded headers. | 429 with `Retry-After`; forged headers do not change the key. |
| Browser database access | After the migration, inspect RLS/grants and attempt reads/writes with Supabase anon and authenticated browser credentials. | No direct access to private application tables. Check `TRUNCATE` grants as well as RLS. |
| Analytics | Open a recovery URL and a private room invitation while inspecting outbound requests and queues. Navigate within the SPA and trigger an action. | No recovery token, code, query string or fragment in analytics URL fields. Authentication and joining still work. |
| Tracing | Run scene analysis, translation, task/clue generation and description evaluation, including invalid output, failover and a cache hit. | Correct nested observations, actual model/provider, usage per outbound call, validation/fallback/cache outcomes; no image bytes, signed URLs or exception text. |
| Tracing outage | Disable credentials or force exporter/setup failures. | Learner behavior and application exceptions remain unchanged. |

The regression suites live in `backend/tests` and `frontend/tests`. Run the
[repository checks](../AGENTS.md#checks-before-opening-a-pull-request), including
PostgreSQL tests with `TEST_DATABASE_URL` pointing only at a disposable migrated
database. The [security workflow](security-checks.md) adds static and dependency
advisory checks. A skipped database test or failed advisory lookup is incomplete
coverage, not a passing security result.

## Deployment checks and remaining work

- Verify `AUTH_MODE=supabase`, an explicit frontend CORS allowlist, the correct
  Supabase issuer/audience, and anonymous-login policy. Demo auth currently has
  only a warning against deployment.
- Verify the Storage bucket is private and review its policies, maximum object
  size and MIME allowlist. Revoke or rotate any previously exposed capabilities
  as needed. Source review cannot establish the deployed bucket configuration.
- Review the access-control migration before deployment. It preserves rows and
  backend access but intentionally removes direct browser-role access. Do not
  apply it to live Supabase as an unreviewed local test.
- Backfill Stripe customer ownership metadata only after verifying account
  ownership. Never infer the link from an email match alone. Durable webhook
  deduplication, ordering and persistence-error retries remain follow-up work.
- Configure edge limits and trusted proxy addresses. Public submission counters
  are per process and reset on restart; they do not provide shared protection
  across replicas. Authenticated support, upload/storage quotas, global LLM
  spending and background-queue capacity need separate operational limits.
- Keep Langfuse content capture off for production until retention, access and
  consent are reviewed. Use backend-only keys and the intended data region. The
  local tests inspect exported spans; a real dashboard smoke test still requires
  the team's Langfuse project. See the backend's AI observability guide.
- Check hosted analytics settings, enhanced automatic collection and session
  replay masking for learner text/photos. URL sanitization does not audit every
  third-party capture channel. Review retention and access to previously
  collected URLs; rotate exposed recovery or invitation capabilities as needed.
- Check TLS, response security headers, dependency versions in the actual
  deployment, restricted database credentials, secret rotation and CI branch
  protection. Automated scans do not replace these checks.

No live learner data was queried, no real support message or payment was sent,
and no live migration was applied during this review.
