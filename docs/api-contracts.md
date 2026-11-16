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
- `POST /api/webhooks/meta/leadgen` — Meta Lead Ads webhook; stores lead with `source=meta_lead_ad` + consent timestamp (Phase 3). Verify-token handshake per Meta docs before any real webhook goes live.
- `POST /api/leads/match` — area → registered dealers matching (Phase 3)
- `POST /api/webhooks/whatsapp` — WhatsApp Cloud API inbound; bot replies ONLY to opted-in/inbound contacts (Phase 4)

## Live (Phase 3 — landing page lead capture)
- `POST /api/leads/capture` — the ONLY public lead-write endpoint. Requires `slug` (business landing page), `name`, `consent: true`, and at least one of phone/email. `consent_timestamp` is recorded SERVER-SIDE. Honeypot `company` field silently rejects bots (400). `source` is fixed to `landing_page`. 201 → `{lead: {id, status}}`.
- `GET /api/public/landing/{slug}` — public, no-auth landing page config. Returns ONLY business display fields (business_name, niche, target_area). Never personal data or other clients' rows. 404 for unknown slugs.
- `GET /api/leads` — auth. The owner's leads, newest first (max 200). Each row carries `source`, `consent_timestamp`, `status`, `metadata`.
- `PATCH /api/leads/{id}/status` — auth. Status ∈ {new, contacted, converted, archived}; other users' leads → 404.
- `GET /api/settings` / `PATCH /api/settings` — auth. Now includes `landing_slug`. PATCH semantics: omitted field = keep existing; `landing_slug: "auto"` derives a slug from the business name (suffix -2, -3… on conflicts); explicit slug validated (`^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$`, reserved words rejected) and globally unique (409 on conflict).
- Landing page URL: `/l/<slug>` (frontend SPA route).

## Ground rules encoded in contracts (Section 0 of the roadmap)
- Every lead write requires a `source` from the allowlist and a `consent_timestamp`.
- No endpoint creates outbound-first contact. `messages.direction=in` rows must exist before the bot replies.
