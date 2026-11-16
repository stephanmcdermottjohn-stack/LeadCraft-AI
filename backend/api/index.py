"""Vercel serverless entry for the LeadCraft AI backend.

Deployed at the project root as api/index.py (Vercel requirement: python
functions live inside the api/ directory). The FastAPI app lives in app/main.py
one level up. Serverless = no background scheduler loop, so
APP_DISABLE_SCHEDULER is forced on and due-post flipping happens lazily on
list reads (see app/api/content.py).
"""
import os
import sys

os.environ.setdefault("APP_DISABLE_SCHEDULER", "1")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.main import app  # noqa: E402  (import after sys.path setup)
