"""认证与权限冒烟测试"""
from app.models import User


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_first_user_is_admin(client, admin_headers):
    from app.database import SessionLocal, get_engine

    with SessionLocal(bind=get_engine()) as db:
        assert db.query(User).filter_by(username="admin1").first().role == "admin"


def test_register_duplicate(client, admin_headers):
    resp = client.post("/api/auth/register", json={"username": "admin1", "password": "x12345"})
    assert resp.status_code == 409


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", data={"username": "admin1", "password": "wrong"})
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.get("/api/tasks").status_code == 401


def test_admin_config_proxy_masks_secrets(client, admin_headers):
    """脱敏逻辑不依赖基座可达：直接单测 _mask_configs"""
    from app.routers.admin import _mask_configs

    masked = _mask_configs(
        {"INSIGHT_ENGINE_API_KEY": "sk-xxx", "HOST": "0.0.0.0", "DB_PASSWORD": "p"}
    )
    assert masked["INSIGHT_ENGINE_API_KEY"] == "******"
    assert masked["DB_PASSWORD"] == "******"
    assert masked["HOST"] == "0.0.0.0"


def test_wx_login_not_implemented(client):
    assert client.post("/api/auth/wx/login", json={"code": "x"}).status_code == 501
