"""Runtime settings, read from environment variables.

Secrets (DATABASE_URL, ADMIN_TOKEN, GEMINI_API_KEY) are only ever read from the
environment. For local development they can be placed in backend/.env, which is
git-ignored. See backend/.env.example for the full list.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
AI_CONFIG_DIR = BACKEND_DIR / "ai_config"
SOURCES_FILE = BACKEND_DIR / "sources.json"

try:  # Optional: load backend/.env for local runs.
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def normalize_database_url(url: str) -> str:
    """Make provider URLs (postgres://, postgresql://) use the psycopg 3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: normalize_database_url(
            os.environ.get("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'local.db').as_posix()}")
        )
    )
    admin_token: str = field(default_factory=lambda: os.environ.get("ADMIN_TOKEN", ""))
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    # Rolling news window, measured from each article's publication time.
    retention_hours: int = field(default_factory=lambda: _int("RETENTION_HOURS", 168))
    # Items dated further than this into the future are rejected as implausible.
    future_tolerance_minutes: int = field(default_factory=lambda: _int("FUTURE_TOLERANCE_MINUTES", 60))
    feed_timeout_seconds: int = field(default_factory=lambda: _int("FEED_TIMEOUT_SECONDS", 15))
    ai_enabled: bool = field(default_factory=lambda: _bool("AI_ENABLED", True))
    # Upper bound on model calls per collection run (protects free-tier quotas).
    ai_max_per_run: int = field(default_factory=lambda: _int("AI_MAX_PER_RUN", 6))
    # Ask AI assistant: per-client burst limit and a daily cap that leaves free
    # quota for the hourly analyses.
    ask_per_client_limit: int = field(default_factory=lambda: _int("ASK_PER_CLIENT_LIMIT", 8))
    ask_daily_limit: int = field(default_factory=lambda: _int("ASK_DAILY_LIMIT", 150))
    background_enabled: bool = field(default_factory=lambda: _bool("BACKGROUND_ENABLED", True))
    background_max_per_run: int = field(default_factory=lambda: _int("BACKGROUND_MAX_PER_RUN", 25))
    wiki_user_agent: str = field(
        default_factory=lambda: os.environ.get(
            "WIKI_USER_AGENT",
            "NewsVista/1.0 (CS403 class project at SVSU; https://www.svsu.edu) httpx/0.28.1",
        )
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    )


settings = Settings()


def load_model_config() -> dict:
    with open(AI_CONFIG_DIR / "model_config.json", encoding="utf-8") as fh:
        return json.load(fh)


def load_sources() -> list[dict]:
    with open(SOURCES_FILE, encoding="utf-8") as fh:
        return json.load(fh)["sources"]
