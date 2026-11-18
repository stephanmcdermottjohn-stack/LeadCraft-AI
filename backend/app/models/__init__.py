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
