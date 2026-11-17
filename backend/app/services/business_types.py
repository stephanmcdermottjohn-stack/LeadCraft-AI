"""Business-type templates (Phase 3D).

Each template powers:
- the Settings dropdown (label),
- a one-click niche prefill (niche_hint),
- optional extra fields on the public landing form (extras), shown when the
  business enables the toggle. Property keeps the legacy keys
  (deal_type/property_type/budget) so existing leads and CSV exports stay
  compatible.

Extra field spec: {key, label, type: text|select, options?: [..]}.
Keys are whitelisted server-side at capture time.
"""

Extra = dict  # {key, label, type, options?}


def _t(key: str, label: str, options: list[str] | None = None) -> Extra:
    if options:
        return {"key": key, "label": label, "type": "select", "options": options}
    return {"key": key, "label": label, "type": "text"}


BUSINESS_TYPES: dict[str, dict] = {
    "": {
        "label": "General / Other",
        "niche_hint": "",
        "extras": [],
    },
    "property": {
        "label": "Property / Real Estate",
        "niche_hint": "real estate agency and dealer services",
        "extras": [
            _t("deal_type", "I want to", ["buy", "rent", "sell"]),
            _t("property_type", "Property type (e.g. 5 Marla house)"),
            _t("budget", "Budget"),
        ],
    },
    "ecommerce": {
        "label": "E-Commerce / Retail Store",
        "niche_hint": "online store and retail products",
        "extras": [
            _t("product_interest", "Product category"),
            _t("order_size", "Order type", ["single item", "bulk order", "reseller"]),
            _t("budget", "Budget"),
        ],
    },
    "hospitality": {
        "label": "Hotel / Guest House",
        "niche_hint": "hotel rooms and guest house bookings",
        "extras": [
            _t("room_type", "Room type", ["standard", "deluxe", "suite", "family room"]),
            _t("guests", "Guests"),
            _t("stay_dates", "Stay dates"),
            _t("budget", "Budget per night"),
        ],
    },
    "restaurant": {
        "label": "Restaurant / Cafe / Catering",
        "niche_hint": "restaurant dining and catering services",
        "extras": [
            _t("service_type", "Service", ["dine-in booking", "home delivery", "event catering"]),
            _t("guests", "Guests / party size"),
            _t("event_date", "Date needed"),
        ],
    },
    "salon": {
        "label": "Salon / Beauty / Spa",
        "niche_hint": "salon, bridal makeup and spa services",
        "extras": [
            _t("service_type", "Service", ["bridal makeup", "haircut / styling", "facial / skin", "spa / massage"]),
            _t("event_date", "Date needed"),
            _t("budget", "Budget"),
        ],
    },
    "health": {
        "label": "Clinic / Healthcare",
        "niche_hint": "clinic consultations and healthcare services",
        "extras": [
            _t("specialty", "Specialty / concern"),
            _t("visit_type", "Visit type", ["in-person", "video consultation"]),
            _t("preferred_time", "Preferred time"),
        ],
    },
    "education": {
        "label": "Education / Coaching / Tuition",
        "niche_hint": "coaching classes and tuition services",
        "extras": [
            _t("subject", "Subject / course"),
            _t("student_level", "Level", ["school", "college", "university", "professional"]),
            _t("class_mode", "Mode", ["in-person", "online"]),
        ],
    },
    "fitness": {
        "label": "Gym / Fitness Trainer",
        "niche_hint": "gym membership and personal training",
        "extras": [
            _t("goal", "Goal", ["weight loss", "muscle gain", "general fitness", "rehab"]),
            _t("plan_type", "Plan", ["gym membership", "personal training", "online coaching"]),
        ],
    },
    "travel": {
        "label": "Travel Agency / Tours",
        "niche_hint": "tour packages and travel bookings",
        "extras": [
            _t("destination", "Destination"),
            _t("travelers", "Travelers"),
            _t("trip_type", "Trip type", ["family trip", "honeymoon", "group tour", "corporate"]),
            _t("budget", "Budget"),
        ],
    },
    "auto": {
        "label": "Car Dealer / Auto Workshop",
        "niche_hint": "car sales and auto services",
        "extras": [
            _t("deal_type", "I want to", ["buy", "sell", "service / repair"]),
            _t("vehicle", "Make / model"),
            _t("budget", "Budget"),
        ],
    },
    "construction": {
        "label": "Construction / Architect",
        "niche_hint": "construction and architectural design services",
        "extras": [
            _t("project_type", "Project", ["new house", "renovation", "commercial", "design only"]),
            _t("area_size", "Plot / area size"),
            _t("budget", "Budget"),
        ],
    },
    "legal": {
        "label": "Lawyer / Legal Services",
        "niche_hint": "legal consultation and representation",
        "extras": [
            _t("case_type", "Matter type", ["property", "family", "corporate", "criminal", "tax"]),
            _t("urgency", "Urgency", ["immediate", "within a week", "planning ahead"]),
        ],
    },
    "events": {
        "label": "Event Management / Wedding Planner",
        "niche_hint": "event planning and wedding services",
        "extras": [
            _t("event_type", "Event type", ["wedding", "mehndi", "corporate", "birthday", "other"]),
            _t("event_date", "Event date"),
            _t("guests", "Expected guests"),
            _t("budget", "Budget"),
        ],
    },
    "photography": {
        "label": "Photography / Studio",
        "niche_hint": "photography and videography services",
        "extras": [
            _t("shoot_type", "Shoot type", ["wedding", "mehndi", "product", "portrait", "video"]),
            _t("event_date", "Date needed"),
            _t("budget", "Budget"),
        ],
    },
    "cleaning": {
        "label": "Cleaning / Maintenance Services",
        "niche_hint": "cleaning, repair and maintenance services",
        "extras": [
            _t("service_type", "Service", ["deep cleaning", "pest control", "repairs", "painting"]),
            _t("property_size", "Property size"),
            _t("preferred_time", "Preferred time"),
        ],
    },
    "finance": {
        "label": "Finance / Insurance / Loans",
        "niche_hint": "insurance policies and loan advisory",
        "extras": [
            _t("product", "Interested in", ["life insurance", "health insurance", "car finance", "home loan", "business loan"]),
            _t("amount", "Amount range"),
        ],
    },
    "it": {
        "label": "IT / Software Services",
        "niche_hint": "software development and IT services",
        "extras": [
            _t("service_type", "Service", ["website / app", "ecommerce store", "SEO / marketing", "IT support"]),
            _t("budget", "Budget"),
        ],
    },
}

EXTRA_VALUE_MAX = 120


def extras_for(business_type: str) -> list[Extra]:
    return BUSINESS_TYPES.get(business_type, {}).get("extras", [])


def is_valid_type(value: str) -> bool:
    return value in BUSINESS_TYPES


def public_extras(business_type: str) -> list[Extra]:
    """Payload for the public landing config (already JSON-safe)."""
    out = []
    for e in extras_for(business_type):
        item = {"key": e["key"], "label": e["label"], "type": e["type"]}
        if "options" in e:
            item["options"] = e["options"]
        out.append(item)
    return out
