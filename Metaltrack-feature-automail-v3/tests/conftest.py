import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="automail-test-")
os.environ.update({
    "DRY_RUN": "true",
    "RUN_QUEUE": "false",          # tests drive the queue by hand with process_once()
    "DB_PATH": str(Path(_tmp) / "test.db"),
    "ATTACHMENT_DIR": str(Path(_tmp) / "att"),
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin-pass",
    "PER_MINUTE_LIMIT": "1000",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "DrPost"))

from fastapi.testclient import TestClient  # noqa: E402
import AutoMailAPI  # noqa: E402
import mail_queue  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(AutoMailAPI.app) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client):
    token = client.post("/api/login", json={"username": "admin", "password": "admin-pass"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def run_queue():
    def run(times=3):
        for _ in range(times):
            mail_queue.process_once(AutoMailAPI.doctor)
    return run
