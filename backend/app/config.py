"""Runtime configuration, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "frontend"
SEED_FILE = ROOT_DIR / "backend" / "seed" / "templates.json"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv. Real env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_json(name: str) -> dict:
    raw = _env(name)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


DEFAULT_SEARCH_DOMAINS = (
    "servicesaustralia.gov.au,homeaffairs.gov.au,myagedcare.gov.au,"
    "ndis.gov.au,ato.gov.au,dva.gov.au,my.gov.au"
)


@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8787))
    db_path: Path = field(
        default_factory=lambda: (ROOT_DIR / _env("DB_PATH", "data/casework.sqlite3")).resolve()
    )
    case_retention_days: int = field(default_factory=lambda: _env_int("CASE_RETENTION_DAYS", 30))
    access_token: str = field(default_factory=lambda: _env("APP_ACCESS_TOKEN"))

    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    jev_url: str = field(
        default_factory=lambda: _env("JEV_URL", "https://openrouter.ai/api/alpha/decisions")
    )
    jev_model: str = field(default_factory=lambda: _env("JEV_MODEL", "typesafe/jev-1.13"))
    jev_timeout: float = field(default_factory=lambda: _env_float("JEV_TIMEOUT_SECONDS", 6.0))
    generate_model: str = field(default_factory=lambda: _env("GENERATE_MODEL"))

    brave_api_key: str = field(default_factory=lambda: _env("BRAVE_API_KEY"))
    google_cse_key: str = field(default_factory=lambda: _env("GOOGLE_CSE_KEY"))
    google_cse_cx: str = field(default_factory=lambda: _env("GOOGLE_CSE_CX"))
    search_cache_hours: int = field(default_factory=lambda: _env_int("SEARCH_CACHE_HOURS", 24))
    search_domains: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            d.strip().lower()
            for d in _env("SEARCH_DOMAINS", DEFAULT_SEARCH_DOMAINS).split(",")
            if d.strip()
        )
    )

    jotform_url: str = field(
        default_factory=lambda: _env("JOTFORM_URL", "https://form.jotform.com/252413844700855")
    )
    jotform_typea_map: dict = field(default_factory=lambda: _env_json("JOTFORM_TYPEA_MAP"))

    office_signoff: str = field(default_factory=lambda: _env("OFFICE_SIGNOFF", "Team Moreton"))
    office_name: str = field(
        default_factory=lambda: _env(
            "OFFICE_NAME", "Office of Julie-Ann Campbell MP, Federal Member for Moreton"
        )
    )
    office_phone: str = field(default_factory=lambda: _env("OFFICE_PHONE"))
    office_email: str = field(default_factory=lambda: _env("OFFICE_EMAIL"))


settings = Settings()
