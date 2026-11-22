"""Application settings loaded from environment variables / .env."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./data/openstudio.db"

    # Clue generation
    dictionary_provider: str = "wordnet"
    dictionary_jsonl_path: str = ""
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"

    # Export fonts
    font_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


_SECRET_TOKEN_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b")


def redact_secrets(text: str) -> str:
    """Mask configured API keys or Anthropic token patterns before logging/persisting errors."""
    out = str(text or "")
    for candidate in (get_settings().anthropic_api_key, os.environ.get("ANTHROPIC_API_KEY", "")):
        if candidate and len(candidate) >= 6:
            out = out.replace(candidate, "[REDACTED]")
    return _SECRET_TOKEN_RE.sub("[REDACTED]", out)

