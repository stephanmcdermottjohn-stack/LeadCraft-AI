# P2 provider modules — design notes (approval required, nothing integrated)

Roadmap: P2 = "design first, then approve". This document is the design gate.
**No provider code, keys, SDKs or data flows exist in the product today.** The
two modules below stay off until the owner approves a monthly budget, a vendor,
and the compliance checklist at the end. Rule honored: paid providers are
never required for core app function.

---

## 1. B2B visitor identification (optional, off by default)

### What it would do
Match a website visit to a **company** (not a person): "3 visits from
`acme.pk` this week". Classic vendors in this class: Leadfeeder/Dealfront,
Albacross, Snitcher, RB2B, Warmly. They typically use the request IP plus
reverse-IP databases.

### What it would NOT do
- No individual-level identification or "email reveal" of visitors.
- No scraping, no purchased contact lists, no outbound-first contact.
- No silent data sharing: a tenant must explicitly enable it.

### Data we would store (minimum)
`visitor_company_events`: `user_id, company_name, company_domain, page_path,
first_seen_at, last_seen_at, source_provider`. **No IP addresses, no raw
headers, no personal names.** Company-level only, tenant-scoped, deletable.

### Architecture (if approved)
1. Server-side lookup at analytics-ingest time or a nightly batch over
   first-party page views (the `analytics_events` table already exists).
2. Provider returns company domain → we cache the mapping for N days to keep
   API calls (cost) down.
3. Report card: companies this week, repeat visits; explicitly labelled
   "company-level estimate — not a person".
4. Per-tenant toggle + global kill switch in env; default **off**.

### Privacy / compliance questions to settle before code
- Is IP→company matching personal data in our target markets? (Legal review,
  not an engineering guess; GDPR legitimate-interest assessment if EU traffic.)
- Privacy-policy disclosure + opt-out route for site visitors.
- Vendor DPA, data residency, retention, whether the vendor stores raw IPs.
- Consent-banner interaction: identification must not depend on cookie consent
  if it is server-side, but the disclosure/opt-out still applies.

### Cost gate (to be filled by vendor quotes — do not guess)
| Vendor | Free tier | Paid model | Data residency | Opt-out | Quote |
|---|---|---|---|---|---|
| Leadfeeder/Dealfront | limited companies/site | per-site monthly | TBD | TBD | TBD |
| Albacross | limited companies | per-site monthly | TBD | TBD | TBD |
| Snitcher | trial | per-site monthly | TBD | TBD | TBD |
| RB2B (person-level) | — | **rejected**: person-level identification conflicts with our rules | — | — | — |

**Decision needed:** monthly cap (e.g. one site, free tier only, or paid),
vendor, and whether B2B identification is worth it for a salon/real-estate
customer base where most leads are individuals.

---

## 2. Voice / telephony (design-only)

### What it could do
Log inbound/outbound calls against a lead, store consent-checked summaries,
surface "call due" next-actions. CallHippo/Twilio-class vendors.

### What it will NOT do
- No auto-dialer, no robocalls, no outbound-first contact.
- No call recording without an explicit, logged consent step.
- No AI voice agent in v1 of any telephony work.

### Architecture sketch (if approved)
1. Provider number rented per business; webhook → `call_events` table
   (`lead_id?, direction, started_at, duration_s, recording_url?`).
2. Inbound calls resolved to a lead by phone match within the tenant; unknown
   numbers create **no** lead automatically (consent rule).
3. Recording off by default; when enabled, a consent prompt plays and the
   consent time is stored with the call row.
4. Timeline merge like inbox messages (`call: inbound 2m 14s`).
5. Owner-initiated click-to-call only; every outbound call requires an
   existing consented lead.

### Pakistan regulatory checklist (must verify, not assume)
- PTA licensing/registration for VoIP termination and number provisioning.
- Business documentation required for local number rental.
- Call-recording consent requirements and storage location.
- Per-minute inbound/outbound rates, number rental, recording storage costs.
- Vendor support for Pakistani numbers and caller ID.

### Cost gate (quotes required)
Per-minute inbound, per-minute outbound, number rental/month, recording
storage, plus any AI STT/TTS/LLM usage if a voice agent is ever proposed.
**No integration until a written monthly cap is approved.**

---

## 3. Approval checklist (owner sign-off)

- [ ] Monthly budget cap per module (hard limit, enforced in code).
- [ ] Vendor chosen + DPA/data-residency reviewed.
- [ ] Privacy policy updated (visitor identification and/or call recording).
- [ ] Opt-out route published for site visitors / callers.
- [ ] Pilot scope (one business, one site/number) and duration.
- [ ] Kill switch tested (env flag turns the module off without deploy).

## 4. Status

Both modules remain **not implemented**. The product continues to work with
zero external cost: first-party analytics, capture-time attribution,
owner-logged reviews/referrals, manual inbox. If approval never comes, nothing
in the core product is blocked.
