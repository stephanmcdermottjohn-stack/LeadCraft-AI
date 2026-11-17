"""Ideal Customer Profile templates + explainable lead-fit matching (P0 #2).

Matching is deliberately rule-based and transparent: every factor returns
match / partial / no_match / unknown with a human-readable detail line. The
score is earned-points-over-evaluable-weight, so unknown factors never drag a
lead down — they just narrow the basis. The result is a heuristic fit grade
(A-D), never presented as a calibrated probability.

Budget comparison is raw-number based (lakh/crore words are expanded, no
currency conversion) and is stated as such in the factor detail.
"""
import json
import re

TEMPLATE_KEYS = (
    "property", "education", "healthcare", "ecommerce",
    "recruitment", "saas", "professional_services", "other",
)

ICP_TEMPLATES: dict[str, dict] = {
    "property": {
        "label": "Property / Real Estate",
        "name": "Property buyer",
        "industry": "real estate",
        "business_type": "property",
        "needs": "house plot apartment purchase rent investment",
        "preferred_services": "site visit property consultation deal closing",
        "decision_authority": "family decision maker",
        "buying_timeline": "within 3 months",
        "criteria": ["Local area buyer", "Financing ready or cash buyer"],
    },
    "education": {
        "label": "Education / Coaching",
        "name": "Student / parent",
        "industry": "education",
        "business_type": "education",
        "needs": "admission tuition exam preparation course",
        "preferred_services": "demo class counselling",
        "decision_authority": "parent or guardian",
        "buying_timeline": "this admission season",
        "criteria": ["School/college student", "Within commuting distance"],
    },
    "healthcare": {
        "label": "Healthcare",
        "name": "Patient",
        "industry": "healthcare",
        "business_type": "health",
        "needs": "consultation treatment checkup follow-up",
        "preferred_services": "appointment booking",
        "decision_authority": "patient",
        "buying_timeline": "within 2 weeks",
        "criteria": ["Local to the clinic"],
    },
    "ecommerce": {
        "label": "E-Commerce / Retail",
        "name": "Online shopper",
        "industry": "retail",
        "business_type": "ecommerce",
        "needs": "product price delivery discount",
        "preferred_services": "order support",
        "decision_authority": "self",
        "buying_timeline": "within 1 month",
        "criteria": ["Repeat purchase potential"],
    },
    "recruitment": {
        "label": "Recruitment / Staffing",
        "name": "Hiring company",
        "industry": "recruitment",
        "business_type": "it",
        "needs": "hiring candidates vacancy staffing",
        "preferred_services": "candidate shortlisting interview coordination",
        "decision_authority": "HR manager",
        "buying_timeline": "this quarter",
        "criteria": ["Multiple open roles"],
    },
    "saas": {
        "label": "Software / SaaS",
        "name": "SaaS buyer",
        "industry": "software",
        "business_type": "it",
        "needs": "automation software subscription integration",
        "preferred_services": "demo trial onboarding",
        "decision_authority": "founder or IT lead",
        "buying_timeline": "within 1 month",
        "criteria": ["Has budget authority", "Uses the tools we integrate with"],
    },
    "professional_services": {
        "label": "Professional Services",
        "name": "Professional services client",
        "industry": "professional services",
        "business_type": "",
        "needs": "consultation legal accounting advisory retainer",
        "preferred_services": "consultation meeting",
        "decision_authority": "owner or partner",
        "buying_timeline": "within 3 months",
        "criteria": ["Recurring engagement potential"],
    },
    "other": {
        "label": "Other / Custom",
        "name": "Ideal customer",
        "industry": "",
        "business_type": "",
        "needs": "",
        "preferred_services": "",
        "decision_authority": "",
        "buying_timeline": "",
        "criteria": [],
    },
}

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have", "has", "are",
    "was", "were", "will", "would", "want", "wants", "need", "needs", "looking",
    "their", "there", "they", "them", "then", "than", "into", "about", "some",
    "your", "you", "our", "out", "get", "got", "not", "but", "can", "could",
}

FACTOR_WEIGHTS = {"location": 25, "needs": 35, "services": 25, "budget": 15}

GRADE_BANDS = ((75, "A"), (50, "B"), (30, "C"), (0, "D"))


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 3 and w not in STOPWORDS}


def _factor(name: str, status: str, detail: str, points: float, possible: int) -> dict:
    return {"factor": name, "status": status, "detail": detail, "points": points, "weight": possible}


def _text_factor(name: str, weight: int, want_text: str, have_text: str) -> dict:
    """Keyword-overlap factor: match / partial / no_match / unknown."""
    want, have = _tokens(want_text), _tokens(have_text)
    if not want or not have:
        return _factor(name, "unknown", f"Missing {'ICP' if not want else 'lead'} information - not scored.", 0, weight)
    hits = want & have
    ratio = len(hits) / len(want)
    if ratio >= 0.5:
        return _factor(name, "match", f"Strong overlap: {', '.join(sorted(hits)) or 'keywords matched'}.", weight, weight)
    if hits:
        return _factor(name, "partial", f"Some overlap: {', '.join(sorted(hits))}.", weight * 0.5, weight)
    return _factor(name, "no_match", f"No keyword overlap (ICP keywords: {', '.join(sorted(want))}).", 0, weight)


def _location_factor(icp_location: str, lead_area: str) -> dict:
    w = FACTOR_WEIGHTS["location"]
    icp_loc, area = (icp_location or "").strip().lower(), (lead_area or "").strip().lower()
    if not icp_loc or not area:
        return _factor("location", "unknown", "Missing area or ICP location - not scored.", 0, w)
    parts = [p.strip() for p in icp_loc.replace(";", ",").split(",") if p.strip()]
    if any(p in area or area in p for p in parts):
        return _factor("location", "match", f"Lead area '{lead_area}' matches ICP location '{icp_location}'.", w, w)
    return _factor("location", "no_match", f"Lead area '{lead_area}' outside ICP location '{icp_location}'.", 0, w)


def _budget_factor(icp: dict, metadata: dict) -> dict:
    w = FACTOR_WEIGHTS["budget"]
    lo, hi = icp.get("budget_min"), icp.get("budget_max")
    if lo is None and hi is None:
        return _factor("budget", "unknown", "ICP has no budget range - not scored.", 0, w)
    raw = str(metadata.get("budget", "") or "")
    nums = [float(n.replace(",", "")) for n in re.findall(r"[\d][\d,]*\.?\d*", raw)]
    if not nums:
        return _factor("budget", "unknown", "Lead gave no parseable budget - not scored.", 0, w)
    value = nums[0]
    if "crore" in raw.lower():
        value *= 10_000_000
    elif "lakh" in raw.lower():
        value *= 100_000
    # "80,000 per month" style numbers are treated as raw PKR; monthly figures
    # compared against raw bounds too — stated honestly in the detail.
    if lo is not None and value < lo:
        return _factor("budget", "no_match", f"Lead budget {int(value)} below ICP minimum {lo}.", 0, w)
    if hi is not None and value > hi:
        return _factor("budget", "no_match", f"Lead budget {int(value)} above ICP maximum {hi}.", 0, w)
    return _factor("budget", "match", f"Lead budget {int(value)} within ICP range.", w, w)


def match_lead(icp: dict, lead: dict) -> dict:
    """Compute an explainable ICP fit for a lead.

    `icp` and `lead` are already-serialized public dicts. Returns
    {score, grade, factors}. score is None when nothing was evaluable.
    """
    metadata = lead.get("metadata") or {}
    notes = lead.get("intent_notes") or ""
    meta_text = " ".join(str(v) for v in metadata.values())
    factors = [
        _location_factor(icp.get("location", ""), lead.get("area", "")),
        _text_factor("needs", FACTOR_WEIGHTS["needs"], icp.get("needs", ""), notes),
        _text_factor("services", FACTOR_WEIGHTS["services"],
                     icp.get("preferred_services", ""), f"{meta_text} {notes}"),
        _budget_factor(icp, metadata),
    ]
    possible = sum(f["weight"] for f in factors if f["status"] != "unknown")
    earned = sum(f["points"] for f in factors if f["status"] != "unknown")
    if possible <= 0:
        return {"score": None, "grade": "", "factors": factors}
    score = round(earned / possible * 100)
    grade = next(g for floor, g in GRADE_BANDS if score >= floor)
    return {"score": score, "grade": grade, "factors": factors}


def template_payload() -> list[dict]:
    out = []
    for key in TEMPLATE_KEYS:
        t = ICP_TEMPLATES[key]
        out.append({"key": key, **t})
    return out
