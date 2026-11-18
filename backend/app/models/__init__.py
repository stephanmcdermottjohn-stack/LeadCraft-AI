"""Core database models (Phase 1 schema, verbatim from the roadmap).

Design notes:
- `leads.consent_timestamp` is NOT NULL: the platform only records leads that
  arrived through a consented channel (Meta Lead Ad, inbound message, or a
  form the business controls). Source + consent time are kept on every row
  for the audit/transparency requirement (roadmap Section 0, rule 5).
- `leads.score`/`status` exist now so Phase 3/4 qualification can fill them
  without another migration.
- `leads.metadata_json` holds property-module extensions (budget range,
  buy/rent/sell, etc.) so `property_leads` does not need a separate table.
"""
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    plan_tier: Mapped[str] = mapped_column(String(50), default="basic")
    # Platform admin (staff account): can read /api/admin/overview stats.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settings: Mapped["ClientSettings"] = relationship(back_populates="user", uselist=False)
    content_posts: Mapped[list["ContentPost"]] = relationship(back_populates="user")
    leads: Mapped[list["Lead"]] = relationship(back_populates="user")


class ClientSettings(Base):
    __tablename__ = "clients_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    niche: Mapped[str] = mapped_column(String(200), default="")
    target_area: Mapped[str] = mapped_column(String(200), default="")
    brand_voice: Mapped[str] = mapped_column(String(500), default="")
    # Public landing page slug: /l/<landing_slug>. Unique; the lead form on
    # that page captures consented leads with source='landing_page'.
    landing_slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    # Phase 3B property module: when on, the landing page shows real-estate
    # extras (buy/rent/sell, property type, budget) and the dashboard surfaces
    # them. Off = plain service-business form.
    show_property_fields: Mapped[bool] = mapped_column(Boolean, default=False)
    # Phase 3D: which business template drives the landing form extras
    # (property, ecommerce, hospitality, ...). "" = general.
    business_type: Mapped[str] = mapped_column(String(50), default="")
    # P0 #5: per-user engagement-score weights (flat dict of ints, JSON).
    # "" = use services.scoring.DEFAULT_WEIGHTS. Editable freely; changing
    # weights never rewrites old snapshots (each history row keeps its own
    # reason breakdown).
    scoring_weights_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="settings")


class ContentPost(Base):
    __tablename__ = "content_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[str] = mapped_column(String(50))
    content_text: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="content_posts")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Allowed values: meta_lead_ad | google_lead_form | landing_page |
    # whatsapp_inbound | direct_message. Anything else must be rejected at
    # the API layer — see ground rules (roadmap Section 0).
    source: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    area: Mapped[str] = mapped_column(String(200), default="")
    intent_notes: Mapped[str] = mapped_column(Text, default="")
    consent_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="new")
    # Property-module extension fields (budget, buy/rent/sell, type...).
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    # --- Phase L (lifecycle engine) -------------------------------------------
    # Sales-funnel lifecycle, separate from the CRM `status` enum above so
    # existing reporting keeps working. Standard stages: capture -> qualify ->
    # nurture -> convert -> retain -> reactivate.
    lifecycle_stage: Mapped[str] = mapped_column(String(30), default="capture")
    grade: Mapped[str] = mapped_column(String(2), default="")  # A-D ICP fit (set by the scoring module)
    assigned_to: Mapped[str] = mapped_column(String(200), default="")
    next_action: Mapped[str] = mapped_column(String(500), default="")
    next_action_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- Source attribution (roadmap P0 #7) ------------------------------------
    campaign: Mapped[str] = mapped_column(String(200), default="")
    utm_source: Mapped[str] = mapped_column(String(200), default="")
    utm_medium: Mapped[str] = mapped_column(String(200), default="")
    utm_content: Mapped[str] = mapped_column(String(200), default="")
    utm_term: Mapped[str] = mapped_column(String(200), default="")
    landing_variant: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="leads")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="lead")
    notes: Mapped[list["LeadNote"]] = relationship(back_populates="lead")
    stage_history: Mapped[list["LeadStageHistory"]] = relationship(back_populates="lead")
    qualification: Mapped["LeadQualification"] = relationship(back_populates="lead", uselist=False)


class LeadStageHistory(Base):
    """Append-only lifecycle stage log (Phase L). Historical rows are never
    rewritten — later ICP/score changes must not corrupt this record."""

    __tablename__ = "lead_stage_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(30))
    to_stage: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(500), default="")
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped[Lead] = relationship(back_populates="stage_history")


class IcpProfile(Base):
    """Ideal Customer Profile (roadmap P0 #2). User-scoped; describes the
    customer the business wants. Lead fit is computed on demand against this
    profile — profiles may be edited or deleted freely without ever rewriting
    historical fit records (those snapshot into lead_score_history later)."""

    __tablename__ = "icp_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    industry: Mapped[str] = mapped_column(String(100), default="")
    company_size: Mapped[str] = mapped_column(String(50), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    # Budget range in PKR raw numbers (UI states the unit). Both nullable:
    # an unset bound simply doesn't constrain the match.
    budget_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mirrors the business template key where relevant ("", property, ...).
    business_type: Mapped[str] = mapped_column(String(50), default="")
    needs: Mapped[str] = mapped_column(String(1000), default="")
    preferred_services: Mapped[str] = mapped_column(String(1000), default="")
    decision_authority: Mapped[str] = mapped_column(String(200), default="")
    buying_timeline: Mapped[str] = mapped_column(String(200), default="")
    # Free-form custom criteria, JSON array of short strings.
    criteria_json: Mapped[str] = mapped_column(Text, default="[]")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadQualification(Base):
    """BANT qualification (roadmap P0 #3). Unknown-first: every dimension
    starts with confidence='unknown' and only becomes 'known' when a value is
    explicitly recorded with its source ('manual' today, 'ai' later).
    'Unknown' is a first-class answer — values are never invented. One row per
    lead, created lazily on first PATCH."""

    __tablename__ = "lead_qualifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Budget: what the customer can/will spend (free text + parsed number kept
    # in value; honest free text, no forced format).
    budget_value: Mapped[str] = mapped_column(String(500), default="")
    budget_confidence: Mapped[str] = mapped_column(String(20), default="unknown")  # known | unknown
    budget_source: Mapped[str] = mapped_column(String(20), default="")             # manual | ai
    # Authority: is this person the decision maker?
    authority_value: Mapped[str] = mapped_column(String(500), default="")
    authority_confidence: Mapped[str] = mapped_column(String(20), default="unknown")
    authority_source: Mapped[str] = mapped_column(String(20), default="")
    # Need: what they actually want.
    need_value: Mapped[str] = mapped_column(String(500), default="")
    need_confidence: Mapped[str] = mapped_column(String(20), default="unknown")
    need_source: Mapped[str] = mapped_column(String(20), default="")
    # Timing: when they intend to buy.
    timing_value: Mapped[str] = mapped_column(String(500), default="")
    timing_confidence: Mapped[str] = mapped_column(String(20), default="unknown")
    timing_source: Mapped[str] = mapped_column(String(20), default="")
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped[Lead] = relationship(back_populates="qualification")


class LeadScoreHistory(Base):
    """Append-only engagement-score + grade snapshots (roadmap P0 #5).
    Historical rows are never recomputed: ICP edits or weight changes must not
    rewrite the past — each row keeps the full factor breakdown it was scored
    with (reason_json). The grade is the ICP-fit snapshot at score time."""

    __tablename__ = "lead_score_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(2), default="")  # ICP-fit snapshot (A-D, "" = unknown)
    # Full explanation: {label, weights: {...}, factors: [{signal, points, weight, detail}]}.
    reason_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadActivity(Base):
    """Lightweight activity log for timeline events that live outside
    dedicated tables (P0 #6): CRM status changes and BANT edits. Notes have
    lead_notes, stage moves have lead_stage_history — those are merged at the
    timeline endpoint. Append-only."""

    __tablename__ = "lead_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # status_changed | qualification_updated (more kinds may follow).
    kind: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LandingVariant(Base):
    """A/B variant for the auto landing page (P1 #1). Overrides headline /
    subtext / CTA label only — the page structure and consent form stay
    template-driven. Empty fields = inherit the control content. The "control"
    arm is the business defaults (no row)."""

    __tablename__ = "landing_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(50))  # e.g. "B", "C" (control = no row)
    headline: Mapped[str] = mapped_column(String(300), default="")
    subtext: Mapped[str] = mapped_column(Text, default="")
    cta_label: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LandingEvent(Base):
    """First-party impression counter for A/B reporting (P1 #1). No cookies,
    no PII: the variant label the landing page served. Submissions and
    qualified-lead counts are computed from leads.landing_variant instead of
    double-tracked here."""

    __tablename__ = "landing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    slug: Mapped[str] = mapped_column(String(100), index=True)
    # "control" or the variant label.
    variant: Mapped[str] = mapped_column(String(50), default="control")
    # impression today (submission/qualified computed from leads later).
    event: Mapped[str] = mapped_column(String(50), default="impression")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NurtureCampaign(Base):
    """Consent-gated drip campaign (P1 #2). Steps are a simple script:
    [{day_offset: days after enrollment, message: the touch text}]. No
    external provider sends anything (zero-cost rule): a due step becomes the
    lead's next_action + a timeline activity, so the owner executes the touch.
    Consent gate: enrollment is only possible for leads with a recorded
    consent_timestamp and never for suppressed contacts."""

    __tablename__ = "nurture_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    # JSON array of {day_offset, message}; validated at the API layer.
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NurtureEnrollment(Base):
    """One lead's place in one campaign. Unique per (campaign, lead)."""

    __tablename__ = "nurture_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("nurture_campaigns.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    # active | completed | stopped | suppressed
    status: Mapped[str] = mapped_column(String(20), default="active")
    steps_total: Mapped[int] = mapped_column(Integer, default=0)  # snapshot at enroll
    current_step: Mapped[int] = mapped_column(Integer, default=0)  # steps surfaced so far
    enrolled_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    next_step_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NurtureSuppression(Base):
    """Per-user do-not-nurture list by phone or email (P1 #2). Consent-gated
    design: a suppressed contact is never enrolled, and enrolling a suppressed
    lead records the enrollment as 'suppressed' instead of active."""

    __tablename__ = "nurture_suppressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Normalized contact value: phone digits or lowercased email.
    value: Mapped[str] = mapped_column(String(320), index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadNote(Base):
    """CRM follow-up notes on a lead (Phase 3C). User-scoped; only the lead's
    owner can read/write. Free-form text, timestamped, append-only (no edit/
    delete in MVP — keeps the audit trail simple)."""

    __tablename__ = "lead_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped[Lead] = relationship(back_populates="notes")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(50))
    last_message_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    lead: Mapped[Lead] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    # in | out (in = lead spoke first; the bot only ever replies, never initiates)
    direction: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
