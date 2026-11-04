"""pytest 夹具：切到 SQLite 测试库并重置引擎"""
import os
import pathlib

TEST_DB = str(pathlib.Path(__file__).parent / "btx_test.db")

os.environ["BTX_DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["BTX_JWT_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import get_engine, init_db, reset_engine_for_tests  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    reset_engine_for_tests()
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except PermissionError:
            pass
    init_db()
    with TestClient(app) as c:
        yield c
    get_engine().dispose()
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except PermissionError:
            pass


@pytest.fixture(scope="session")
def admin_headers(client):
    # 幂等：若因残留库导致用户已存在，直接登录
    resp = client.post(
        "/api/auth/register", json={"username": "admin1", "password": "secret123"}
    )
    if resp.status_code == 409:
        resp = client.post("/api/auth/login", data={"username": "admin1", "password": "secret123"})
    else:
        assert resp.status_code == 201, resp.text
        resp = client.post(
            "/api/auth/login", data={"username": "admin1", "password": "secret123"}
        )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
