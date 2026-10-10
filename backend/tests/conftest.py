import os
import tempfile
from pathlib import Path

# Must be set before the app (and its frozen settings) is imported.
_TMP = Path(tempfile.mkdtemp(prefix="constitbrief-test-"))
os.environ.update({
    "DB_PATH": str(_TMP / "test.sqlite3"), "COOKIE_SECURE": "false", "ANALYSIS_PROVIDER": "rules",
    "OPENROUTER_API_KEY": "", "GENERATE_MODEL": "", "BRAVE_API_KEY": "", "GOOGLE_CSE_KEY": "",
    "GOOGLE_CSE_CX": "", "JOTFORM_API_KEY": "", "JOTFORM_PREFILL_CONTACT": "false",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import auth, db  # noqa: E402
from backend.app.config import settings  # noqa: E402
from backend.app.main import app  # noqa: E402

PASSWORD = "synthetic-pass-1"
HDR = {"X-ConstitBrief": "1"}


@pytest.fixture(scope="session", autouse=True)
def users():
    db.init_db()
    ids = {name: auth.create_user(name, name.title(), PASSWORD, role)
           for name, role in (("alex", "staff"), ("blair", "staff"), ("admin", "admin"))}
    return ids


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD}, headers=HDR)
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def anon():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.headers.update(HDR)
        yield _login(c, "alex")


@pytest.fixture()
def other():
    with TestClient(app) as c:
        c.headers.update(HDR)
        yield _login(c, "blair")


@pytest.fixture()
def admin():
    with TestClient(app) as c:
        c.headers.update(HDR)
        yield _login(c, "admin")


@pytest.fixture()
def set_setting():
    original = {}

    def _set(name, value):
        original.setdefault(name, getattr(settings, name))
        object.__setattr__(settings, name, value)

    yield _set
    for name, value in original.items():
        object.__setattr__(settings, name, value)
