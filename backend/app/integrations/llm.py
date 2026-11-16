"""LLM integration for content generation.

Providers:
- `mock` (default, ALWAYS available): deterministic offline templates, every
  option clearly labeled [MOCK]. Zero network, zero cost. Lets the whole
  product work before any key exists.
- `gemini` (free tier): Google AI Studio key (https://aistudio.google.com/api-keys,
  no credit card). Endpoint VERIFIED from official docs (2026-11-16):
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  header x-goog-api-key; text at candidates[0].content.parts[*].text.
  Free-tier caveat (from Google docs): prompts/responses may be used by
  Google to improve products; rate limits are lower than paid tiers.

An adapter NEVER makes a network call without its credential present; a
missing key is a typed error, not a silent mock fallback.
"""
import re
import time
from dataclasses import dataclass

import httpx


class LLMError(Exception):
    def __init__(self, provider: str, code: str, message: str):
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.message = message


@dataclass
class ContentRequest:
    business_name: str
    niche: str
    target_area: str
    brand_voice: str
    platform: str
    tone: str
    count: int


def build_content_prompt(req: ContentRequest) -> str:
    """Dynamic prompt from clients_settings — personalized per client, not generic."""
    return (
        f"You write social media marketing content for a real business.\n"
        f"Business name: {req.business_name}\n"
        f"Niche: {req.niche or 'general local business'}\n"
        f"Target area: {req.target_area or 'not specified'}\n"
        f"Brand voice: {req.brand_voice or 'friendly and professional'}\n\n"
        f"Write {req.count} distinct {req.tone} post options for {req.platform}.\n"
        f"Rules:\n"
        f"- Each option is 1-3 sentences plus 0-3 relevant hashtags.\n"
        f"- Use only the facts above; never invent prices, offers, dates, statistics, or claims.\n"
        f"- No emojis beyond tasteful minimal use.\n"
        f"- Separate the {req.count} options with a line containing only ---\n"
    )


def parse_options(text: str, count: int) -> list[str]:
    parts = [p.strip() for p in re.split(r"^---$", text.strip(), flags=re.MULTILINE) if p.strip()]
    if not parts:
        raise LLMError("llm", "empty-response", "The model returned no parseable options.")
    return parts[:count]


# --- Gemini (free tier) ------------------------------------------------------

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"


def gemini_generate_text(
    prompt: str,
    api_key: str,
    model: str,
    timeout_s: float = 60.0,
    max_attempts: int = 3,
    retry_delays_s: tuple[float, ...] = (2.0, 6.0),
) -> str:
    if not api_key:
        raise LLMError(
            "gemini",
            "missing-credentials",
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/api-keys (no credit card), "
            "then set LLM_PROVIDER=gemini and GEMINI_API_KEY in backend/.env. Mock provider is used meanwhile.",
        )
    # Gemini returns 503 UNAVAILABLE ("high demand") intermittently on free
    # tier; official guidance is exponential backoff + retry. 429/401/403 are
    # NOT retried (rate limit needs waiting / key is broken).
    last_error: LLMError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(
                f"{GEMINI_BASE_URL}/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=timeout_s,
            )
        except httpx.HTTPError as exc:
            last_error = LLMError("gemini", "network-error", f"Gemini API unreachable: {exc}")
        else:
            if response.status_code == 429:
                raise LLMError("gemini", "rate-limited", "Gemini free-tier rate limit hit; retry in a minute.")
            if response.status_code in (401, 403):
                raise LLMError("gemini", "invalid-credentials", "Gemini rejected the API key (check GEMINI_API_KEY).")
            if response.status_code == 503 and attempt < max_attempts:
                delay = retry_delays_s[min(attempt - 1, len(retry_delays_s) - 1)]
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise LLMError("gemini", "api-error", f"Gemini API error {response.status_code}: {response.text[:200]}")

            try:
                body = response.json()
                candidates = body["candidates"]
                parts = candidates[0]["content"]["parts"]
                text = "".join(str(p.get("text", "")) for p in parts)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMError(
                    "gemini", "unexpected-response", f"Unrecognized Gemini response shape: {str(body)[:200]}"
                ) from exc
            if not text.strip():
                raise LLMError("gemini", "empty-response", "Gemini returned an empty completion.")
            return text

        if attempt < max_attempts:
            delay = retry_delays_s[min(attempt - 1, len(retry_delays_s) - 1)]
            time.sleep(delay)
    raise last_error or LLMError("gemini", "api-error", "Gemini call failed after retries.")


# --- Router ------------------------------------------------------------------

def generate_options(req: ContentRequest, provider: str, gemini_api_key: str, gemini_model: str) -> dict:
    """Returns {provider, options, notice}. Never throws for provider choice —
    unknown provider names fall back to mock with an honest notice."""
    notice = None
    if provider == "gemini":
        text = gemini_generate_text(build_content_prompt(req), gemini_api_key, gemini_model)
        options = parse_options(text, req.count)
    else:
        if provider != "mock":
            notice = f"Unknown LLM provider '{provider}'; used the offline mock instead."
        options = mock_options(req)
        notice = (notice + " " if notice else "") + "Options are [MOCK] templates (no AI key configured)."
    return {"provider": "gemini" if provider == "gemini" else "mock", "options": options, "notice": notice}


def mock_options(req: ContentRequest) -> list[str]:
    """Deterministic offline templates. Honest: every option is labeled [MOCK]
    and never claims facts the profile does not state."""
    niche = req.niche or "our services"
    area = req.target_area or "your area"
    voice = req.brand_voice or "friendly"
    options = [
        f"[MOCK] Looking for {niche} in {area}? {req.business_name} keeps it simple — quality work, "
        f"{voice} service, and no pressure. Message us to get started.",
        f"[MOCK] {req.business_name} — {niche} done right in {area}. "
        f"We keep every step clear, {voice}, and on your schedule. DM us for details.",
        f"[MOCK] Your neighbors in {area} trust {req.business_name} for {niche}. "
        f"Curious what we can do for you? Send us a message today.",
    ]
    return options[: req.count]
