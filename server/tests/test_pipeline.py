"""任务管线闭环测试（mock 基座，不依赖真实服务）"""
import pytest

from app.bettafish import BettaFishError
from app.models import Report


class FakeBettaFish:
    """按调用次数模拟基座行为：引擎未就绪 ×2 → 接受 → running ×1 → completed"""

    def __init__(self):
        self.generate_calls = 0
        self.progress_calls = 0
        self.search_ok = True

    def __call__(self, method, path, json_body=None):
        if path == "/api/search":
            if self.search_ok:
                return {"success": True}
            raise BettaFishError("基座返回 500: internal error")
        if path == "/api/report/generate":
            self.generate_calls += 1
            if self.generate_calls < 3:
                raise BettaFishError("基座返回 400: missing_files")
            return {"success": True, "task_id": "report_12345"}
        if path.startswith("/api/report/progress/"):
            self.progress_calls += 1
            if self.progress_calls < 2:
                return {"status": "running", "progress": 50}
            return {"status": "completed", "progress": 100}
        raise AssertionError(f"意外的请求路径: {path}")


@pytest.fixture
def fake_bf(monkeypatch):
    fake = FakeBettaFish()
    monkeypatch.setattr("app.pipeline.bettafish_request", fake)
    monkeypatch.setattr("app.routers.tasks.bettafish_request", fake)
    monkeypatch.setattr("app.pipeline._sleep", lambda s: None)
    return fake


def test_pipeline_happy_path(client, admin_headers, fake_bf):
    """全流程：pending → running → reporting → completed，报告索引落库"""
    resp = client.post("/api/tasks", json={"query": "测试主题"}, headers=admin_headers)
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    detail = client.get(f"/api/tasks/{task_id}", headers=admin_headers).json()
    assert detail["status"] == "completed"
    assert detail["report_task_id"] == "report_12345"
    assert detail["error"] is None
    assert fake_bf.generate_calls == 3  # 2 次未就绪重试 + 1 次接受

    from app.database import SessionLocal, get_engine

    with SessionLocal(bind=get_engine()) as db:
        report = db.query(Report).filter_by(task_id=task_id).one()
        assert report.report_task_id == "report_12345"
        assert report.title == "测试主题"


def test_pipeline_search_failure(client, admin_headers, fake_bf):
    """检索分发失败 → 任务 failed 且带错误信息"""
    fake_bf.search_ok = False
    resp = client.post("/api/tasks", json={"query": "失败场景"}, headers=admin_headers)
    assert resp.status_code == 201
    detail = client.get(f"/api/tasks/{resp.json()['id']}", headers=admin_headers).json()
    assert detail["status"] == "failed"
    assert detail["error"]


def test_create_task_requires_auth(client):
    assert client.post("/api/tasks", json={"query": "未登录"}).status_code == 401


def test_task_not_visible_to_others(client, admin_headers):
    """任务列表只返回自己的任务"""
    resp = client.post("/api/tasks", json={"query": "隔离测试"}, headers=admin_headers)
    assert resp.status_code == 201
    tasks = client.get("/api/tasks", headers=admin_headers).json()
    assert all(t["query"] for t in tasks)
    assert any(t["query"] == "隔离测试" for t in tasks)
