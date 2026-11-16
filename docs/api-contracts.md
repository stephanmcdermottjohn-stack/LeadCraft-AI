# Virtual Marketing & Lead Generation Platform — API Contracts (living doc)

Base URL (dev): `http://127.0.0.1:8000`

## GET /api/health
Liveness + integration configuration status. **Auth: none (liveness probe).**

Response 200:
```json
{
  "status": "ok",
  "app": "virtual-marketing-platform",
  "version": "0.1.0",
  "environment": "development",
  "integrations": {
    "anthropic_configured": false,
    "whatsapp_configured": false
  }
}
```

## Planned (defined now, implemented in later phases — do not call yet)
- `POST /api/auth/register` · `POST /api/auth/login` — session auth (Phase 1.5)
- `POST /api/content/generate` — niche + platform + tone → Claude caption options (Phase 2)
- `POST /api/content/schedule` — save post + scheduled time (Phase 2)
- `POST /api/webhooks/meta/leadgen` — Meta Lead Ads webhook; stores lead with `source=meta_lead_ad` + consent timestamp (Phase 3). Verify-token handshake per Meta docs before any real webhook goes live.
- `POST /api/leads/capture` — landing-page form submissions, `source=landing_page` (Phase 3)
- `POST /api/leads/match` — area → registered dealers matching (Phase 3)
- `POST /api/webhooks/whatsapp` — WhatsApp Cloud API inbound; bot replies ONLY to opted-in/inbound contacts (Phase 4)

## Ground rules encoded in contracts (Section 0 of the roadmap)
- Every lead write requires a `source` from the allowlist and a `consent_timestamp`.
- No endpoint creates outbound-first contact. `messages.direction=in` rows must exist before the bot replies.
