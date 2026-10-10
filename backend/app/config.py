"""Runtime configuration, read from environment variables (and an optional .env file)."""
from __future__ import annotations

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


def _default_db() -> str:
    return "/tmp/constitbrief.sqlite3" if os.environ.get("VERCEL") else "data/constitbrief.sqlite3"


DEFAULT_SEARCH_DOMAINS = (
    "servicesaustralia.gov.au,homeaffairs.gov.au,myagedcare.gov.au,"
    "ndis.gov.au,ato.gov.au,dva.gov.au,my.gov.au"
)


@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8787))
    db_path: Path = field(
        default_factory=lambda: (ROOT_DIR / _env("DB_PATH", _default_db())).resolve()
    )
    # On serverless hosts (Vercel) only /tmp is writable and it is per-instance and temporary.
    on_vercel: bool = field(default_factory=lambda: bool(os.environ.get("VERCEL")))
    # Creates this admin account if the database has no users (needed where the CLI can't run).
    bootstrap_admin_username: str = field(default_factory=lambda: _env("BOOTSTRAP_ADMIN_USERNAME"))
    bootstrap_admin_password: str = field(default_factory=lambda: _env("BOOTSTRAP_ADMIN_PASSWORD"))
    # Server-side interaction drafts (notes + record) are deleted after this many hours.
    draft_retention_hours: int = field(default_factory=lambda: _env_int("DRAFT_RETENTION_HOURS", 72))
    session_hours: int = field(default_factory=lambda: _env_int("SESSION_HOURS", 10))
    # Set false only for plain-http localhost development.
    cookie_secure: bool = field(default_factory=lambda: _env("COOKIE_SECURE", "true").lower() != "false")

    # Analysis provider: "rules" (default, nothing leaves the server) or "jev".
    analysis_provider: str = field(default_factory=lambda: _env("ANALYSIS_PROVIDER", "rules").lower())
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    jev_url: str = field(
        default_factory=lambda: _env("JEV_URL", "https://openrouter.ai/api/alpha/decisions")
    )
    jev_model: str = field(default_factory=lambda: _env("JEV_MODEL", "typesafe/jev-1.13"))
    jev_timeout: float = field(default_factory=lambda: _env_float("JEV_TIMEOUT_SECONDS", 3.0))
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

    # Jotform handoff. Only the enquiry option goes in the URL by default; contact details
    # only if the office explicitly opts in. Notes/identifiers never go in a URL.
    jotform_prefill_type: bool = field(
        default_factory=lambda: _env("JOTFORM_PREFILL_TYPE", "true").lower() == "true")
    jotform_prefill_contact: bool = field(
        default_factory=lambda: _env("JOTFORM_PREFILL_CONTACT", "false").lower() == "true")
    # Form to hand off to. Override only to point a staging deployment at a cloned test form
    # (same structure) for routing verification.
    jotform_form_id: str = field(default_factory=lambda: _env("JOTFORM_FORM_ID", "252413844700855"))
    # Optional READ-ONLY use of the Jotform API to confirm a submission by its reference.
    jotform_api_key: str = field(default_factory=lambda: _env("JOTFORM_API_KEY"))
    jotform_api_base: str = field(
        default_factory=lambda: _env("JOTFORM_API_BASE", "https://api.jotform.com"))

    office_signoff: str = field(default_factory=lambda: _env("OFFICE_SIGNOFF", "Team Moreton"))
    office_name: str = field(
        default_factory=lambda: _env(
            "OFFICE_NAME", "Office of Julie-Ann Campbell MP, Federal Member for Moreton"
        )
    )
    office_phone: str = field(default_factory=lambda: _env("OFFICE_PHONE"))
    office_email: str = field(default_factory=lambda: _env("OFFICE_EMAIL"))


settings = Settings()


def storage_is_ephemeral() -> bool:
    return settings.on_vercel and str(settings.db_path).startswith("/tmp")
