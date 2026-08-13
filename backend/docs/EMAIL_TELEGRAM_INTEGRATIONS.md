# Gmail → AI draft → Telegram approval

This integration extends the workforce connector, workflow, tool-policy, and canonical approval
runtime. Gmail and Telegram are native provider adapters; workflow state remains in
`WorkflowRun`/`WorkflowStepRun`, and Telegram never sends email directly.

## Setup

1. Create a Google OAuth web client and set `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, and `GOOGLE_OAUTH_REDIRECT_URI`.
2. Enable the Gmail API. The connector requests Gmail read/modify/compose/send plus identity
   scopes. Restrict these in Google Cloud and review consent-screen requirements.
3. Create a Pub/Sub topic in `GOOGLE_PUBSUB_TOPIC` and grant Gmail's push service permission to
   publish. Configure an authenticated push subscription to
   `/api/v1/workforce/webhooks/gmail`. Set its OIDC audience to
   `GOOGLE_PUBSUB_AUDIENCE` and service account to
   `GOOGLE_PUBSUB_SERVICE_ACCOUNT_EMAIL`. `GOOGLE_PUBSUB_VERIFICATION_TOKEN` is only a
   development/test fallback and is rejected in production.
4. Create a Telegram bot, install the `telegram` connector with `bot_token`, and configure its
   webhook at `/api/v1/workforce/webhooks/telegram`. Pass `TELEGRAM_WEBHOOK_SECRET` to
   Telegram's `setWebhook` `secret_token`. The authenticated
   `/connectors/telegram/{installation_id}/configure-webhook` endpoint registers it from
   `TELEGRAM_WEBHOOK_BASE_URL`.
5. Set `TELEGRAM_BOT_USERNAME`. The Telegram link API creates a short-lived, single-use deep
   link. A `/start <token>` message binds that Telegram user/chat to the authenticated Troop
   owner.
6. Seed connector/tool definitions, install the email workflow template, fill both explicit
   connector installation IDs, then publish. Publishing registers the Gmail watch and a
   `TriggerSubscription`.

Run a dedicated Celery worker for the `integrations` queue and Celery Beat. Beat renews Gmail
watches before expiration. Webhooks only validate, normalize, persist, enqueue, and return.

## Security model

- OAuth uses authorization code, state, PKCE, encrypted access/refresh tokens, short-lived
  single-use state, token refresh, and revocation.
- Every provider action requires an explicit `connector_installation_id`; owner/company checks
  run again during execution.
- Pub/Sub validates Google's signed OIDC JWT (issuer, audience, service-account email, expiry).
  Telegram validates its secret-token header. Both reject oversized/malformed JSON and use
  durable dedupe/interaction rows.
- Email HTML is conservatively sanitized. Attachment metadata is retained without automatically
  downloading attachment bodies.
- Gmail send is high-risk and policy-gated. Approval binds workflow, node, account, draft,
  recipients, subject, body, attachments, and exact arguments hash.
- The workflow consumes approval once. Send claims a separate unique idempotency key and checks
  the current thread fingerprint before calling `drafts.send`.
- Access tokens, refresh tokens, bot tokens, OAuth verifier values, and webhook secrets are not
  returned by normal connector APIs.

## Operations and troubleshooting

- `reauthorization_required`: Google rejected refresh; reconnect Gmail.
- `cursor_expired`: Gmail history is too old; refresh the watch and reconcile mailbox state
  before accepting new automatic processing.
- `renewal_failed`: inspect worker connectivity/Google quota, then retry watch renewal.
- `stale`: a new message changed the thread after drafting; the approved draft is not sent.
- Telegram `403`: webhook secret, identity binding, tenant, or pending approval did not match.
- Duplicate Pub/Sub notifications, callbacks, and Celery retries are expected and handled by
  database uniqueness/single-use checks.

For local tests, mock Gmail/Telegram HTTP responses and submit fake Pub/Sub envelopes. Production
security is not weakened for local mode; webhook secrets remain mandatory.
