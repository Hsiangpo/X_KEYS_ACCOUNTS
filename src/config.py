"""Runtime configuration constants."""

from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
STATE_DIR = ROOT_DIR / "state"
OUTPUT_DIR = ROOT_DIR / "output"

DEFAULT_ACCOUNTS_FILE = DOCS_DIR / "Accounts.txt"
DEFAULT_KEYS_FILE = DOCS_DIR / "Keys.txt"
DEFAULT_COOKIES_FILE = STATE_DIR / "cookies.json"
DEFAULT_OUTPUT_DIR = OUTPUT_DIR

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_RATE_LIMIT_RESET_BUFFER_SECONDS = int(
    os.getenv("X_RATE_LIMIT_RESET_BUFFER_SECONDS", "2")
)
DEFAULT_MAX_RATE_LIMIT_WAIT_SECONDS = int(
    os.getenv("X_MAX_RATE_LIMIT_WAIT_SECONDS", "900")
)
DEFAULT_RATE_LIMIT_FALLBACK_WAIT_SECONDS = int(
    os.getenv("X_RATE_LIMIT_FALLBACK_WAIT_SECONDS", "180")
)
DEFAULT_RATE_LIMIT_PROACTIVE_THRESHOLD = int(
    os.getenv("X_RATE_LIMIT_PROACTIVE_THRESHOLD", "0")
)
DEFAULT_LOGIN_TIMEOUT_SECONDS = 420
DEFAULT_LOGIN_BROWSER_CHANNELS = tuple(
    channel.strip()
    for channel in os.getenv("X_LOGIN_BROWSER_CHANNELS", "chrome,msedge").split(",")
    if channel.strip()
)

# Captured via Chrome MCP on 2026-02-19. Can be overridden when X rotates query IDs.
DEFAULT_SEARCH_TIMELINE_QUERY_ID = os.getenv(
    "X_SEARCH_TIMELINE_QUERY_ID",
    "cGK-Qeg1XJc2sZ6kgQw_Iw",
)

DEFAULT_BEARER_TOKEN = os.getenv(
    "X_BEARER_TOKEN",
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
)
