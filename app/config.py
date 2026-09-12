"""Central place for env-driven configuration. Load once, import everywhere."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

WATCHLIST_FILE = DATA_DIR / "watchlist.json"
SAMPLE_PRODUCT_FILE = DATA_DIR / "sample_product.json"

STEEL_API_KEY = os.getenv("STEEL_API_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

# Who gets notified. Single shared watchlist, no accounts -> one address.
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "PriceWatch <onboarding@resend.dev>")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", str(24 * 60 * 60)))
STEEL_MAX_CONCURRENCY = int(os.getenv("STEEL_MAX_CONCURRENCY", "5"))
PAGE_NAV_TIMEOUT_MS = int(os.getenv("PAGE_NAV_TIMEOUT_MS", "30000"))

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
