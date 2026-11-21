# P4 — Integrations & real-time capture (zero-cost, credentials optional)

Goal: stop relying on manual CSV imports. Capture Meta Lead Ads and WhatsApp
inbound messages in real time, while keeping every ground rule from the
roadmap: consent-based, source + consent timestamp on every lead, tenant
isolation, honest labels, no outbound-first contact, no auto-send.

Everything here works with **zero external cost**: the platform has no paid
dependency, and each webhook stays disabled (HTTP 503) until its credentials
are configured. Live activation needs the owner's Meta app credentials; the
code, tests and UI are complete without them.

## Module 1 — Webhook core (shipped)

- `webhook_events` append-only log: `source`, unique provider-scoped
  `event_key`, `status`, `user_id` (nullable), raw `payload_json` (capped),
  `signature_valid`, `lead_id`, `error`, `received_at`, `processed_at`.
- `X-Hub-Signature-256` HMAC-SHA256 verification with constant-time compare.
  An unconfigured App Secret means the endpoint refuses deliveries with 503 —
  unverified payloads are never accepted.
- Store-first, interpret-second: the delivery row is committed before routing,
  so a Graph failure or an unknown page id is visible instead of lost.
- Idempotent: a provider retry returns `duplicates` and creates nothing.
- Statuses: `received | processed | ignored | unrouted |
  pending_credentials | error`. A provider retry is not stored again; the
  response counts it as a `duplicate`.
- `GET /api/integrations/events` (owner/admin) + `GET /api/integrations/events/{id}`
  (payload detail) + `POST .../retry` for `unrouted`, `pending_credentials`,
  `error` and stale `received` rows. Unrouted rows have `user_id = NULL` and
  are never shown to a workspace.

## Module 2 — Meta Lead Ads (shipped, inactive until credentials)

- `GET /api/webhooks/meta` — `hub.mode=subscribe` handshake; 503 without
  `META_VERIFY_TOKEN`, 403 on a wrong token, else echoes `hub.challenge`.
- `POST /api/webhooks/meta` — verified, stored, routed by
  `clients_settings.meta_page_id`.
- Without `META_PAGE_ACCESS_TOKEN` the delivery is kept as
  `pending_credentials` (retry after adding the token). With it, the platform
  fetches `field_data` from Graph API and maps common answer names
  (`full_name`, `phone_number`, `email`, `city`, …) onto the lead; every
  unknown answer is preserved in `metadata.answers`.
- Creates one lead per `leadgen_id` with `source='meta_lead_ad'`,
  `consent_timestamp` = server receipt time (never a client-supplied clock),
  stage history entry, and `utm_source='meta'`. Missing phone **and** email is
  stored as `error` — no unusable lead is created.
- Consent statement: the person submitted a Lead Ad form on Meta; the form
  carries Meta's lead-consent language. The platform records only the time it
  actually received the notification.

## Module 3 — WhatsApp Cloud API inbound (shipped, inactive until credentials)

- `GET /api/webhooks/whatsapp` — same handshake contract.
- `POST /api/webhooks/whatsapp` — verified, stored, routed by
  `clients_settings.whatsapp_phone_number_id`.
- Text / button / interactive replies are stored as inbound messages. Media is
  **labelled** (`[image received - media not downloaded]`) and never fetched.
  Delivery-status callbacks are acknowledged and ignored.
- Unknown sender → one consented lead (`source='whatsapp_inbound'`, inbound
  timestamp) + a `whatsapp_inbound` conversation + the inbound message.
  Known sender → reuses the lead and conversation. **No auto-reply is sent.**
- Idempotent per WhatsApp message id.

## Module 4 — Ops visibility (shipped)

- Settings → **Integrations — inbound capture** card: readiness chips (app
  secret / verify token / page token / Meta ready / WhatsApp ready), both
  webhook URLs, Meta Page id and phone number id fields with numeric
  validation, and the recent delivery table with a Retry action.
- Delivery payloads are owner/admin only (they contain contact details);
  agents/viewers get 403, unauth gets 401.
- Credentials are **never** returned to the browser — only booleans.

## Activation checklist (owner)

1. Create/confirm the Meta app; add the **Webhooks** product.
2. Set server env vars: `META_APP_ID`, `META_APP_SECRET`,
   `META_VERIFY_TOKEN`, `META_PAGE_ACCESS_TOKEN` (and `WHATSAPP_ACCESS_TOKEN`
   only when outbound sends are approved — inbound works without it).
3. In the Meta app, subscribe the Page to `leadgen` and the WhatsApp account to
   `messages`, pointing at:
   - `https://<api-host>/api/webhooks/meta`
   - `https://<api-host>/api/webhooks/whatsapp`
4. Paste the numeric Page id / phone number id in Settings → Integrations.
5. Submit a test Lead Ad form / send a WhatsApp message; the delivery appears
   in the event log with status `processed` and the lead is in Leads.

## Explicitly out of scope (not built)

- Outbound WhatsApp sends / auto-replies (needs an approved template + send
  path; the consent rule forbids outbound-first).
- Instagram DM, Messenger, Google Lead Form webhooks (manual import remains).
- Media download, transcription, attachments.
- Automatic Page subscription via API (must be done in the Meta dashboard).
- Billing/metering per integration (still no payment gateway).
