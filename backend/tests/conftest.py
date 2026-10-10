import os
import tempfile
from pathlib import Path

# Must be set before the app (and its frozen settings) is imported.
_TMP = Path(tempfile.mkdtemp(prefix="casework-test-"))
os.environ["DB_PATH"] = str(_TMP / "test.sqlite3")
for k in ("OPENROUTER_API_KEY", "GENERATE_MODEL", "BRAVE_API_KEY", "GOOGLE_CSE_KEY",
          "GOOGLE_CSE_CX", "APP_ACCESS_TOKEN", "JOTFORM_TYPEA_MAP"):
    os.environ[k] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.config import settings  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def set_setting():
    """Temporarily override a field on the frozen settings object."""
    original = {}

    def _set(name, value):
        original.setdefault(name, getattr(settings, name))
        object.__setattr__(settings, name, value)

    yield _set
    for name, value in original.items():
        object.__setattr__(settings, name, value)
