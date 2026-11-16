"""Vercel serverless entry for the LeadCraft AI backend.

The FastAPI app lives in backend/app/main.py; this thin wrapper points the
@vercel/python runtime at it. Serverless = no background scheduler loop, so
APP_DISABLE_SCHEDULER is forced on here and due-post flipping happens lazily
on list reads (see app/api/content.py).
"""
import os
import sys

# Force-disable the background worker loop: serverless invocations cannot
# keep an asyncio task alive between requests.
os.environ.setdefault("APP_DISABLE_SCHEDULER", "1")

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app  # noqa: E402  (import after sys.path setup)
