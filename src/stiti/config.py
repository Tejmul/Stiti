"""Runtime configuration. Secrets come from .env (never committed)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")


@dataclass(frozen=True)
class Config:
    db_url: str = os.getenv("STITI_DB", "postgresql:///stiti")
    home: Path = Path(os.path.expanduser(os.getenv("STITI_HOME", "~/.stiti")))
    tz: ZoneInfo = ZoneInfo(os.getenv("STITI_TZ", "Asia/Kolkata"))
    briefing_token_budget: int = 1500
    keys: dict[str, str] = field(default_factory=lambda: {
        **{p: os.getenv(f"{p.upper()}_API_KEY", "")
           for p in ("groq", "cerebras", "zai", "cloudflare", "openrouter", "mistral", "nvidia", "gemini")},
        "cloudflare_account": os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
    })


CFG = Config()
CFG.home.mkdir(parents=True, exist_ok=True)
