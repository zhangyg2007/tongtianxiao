"""任务管线：search 分发 → 等待引擎产出 → 触发报告生成 → 轮询完成 → 落报告索引

基座是无任务态的：/api/search 只是分发检索，报告需等三个引擎产出输入文件后
POST /api/report/generate 触发。管线在后台线程串起全流程并回写任务状态：

    pending → running（search 已分发）
            → reporting（报告 task_id 已获得）
            → completed / failed
"""
import time

from .bettafish import BettaFishError, bettafish_request
from .config import get_settings
from .models import AnalysisTask, Report


def _sleep(seconds: float) -> None:
    """可注入的 sleep（测试中替换为 no-op）"""
    time.sleep(seconds)


def _fail(db, task: AnalysisTask, error: str) -> None:
    task.status = "failed"
    task.error = error[:500]
    db.commit()


def run_pipeline(task_id: int, query: str) -> None:
    from .database import SessionLocal

    settings = get_settings()
    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, task_id)
        if task is None:
            return

        # ---- 1. 分发检索分析 ----
        try:
            resp = bettafish_request("POST", "/api/search", json_body={"query": query})
            if not resp.get("success"):
                _fail(db, task, f"基座拒绝检索请求: {str(resp)[:300]}")
                return
        except BettaFishError as exc:
            _fail(db, task, str(exc))
            return
        task.status = "running"
        db.commit()

        # ---- 2. 等待引擎产出并触发报告生成 ----
        # 引擎爬取分析耗时较长（数十分钟），期间 generate 返回 400（missing_files）；
        # 另外基座同一时刻只允许一个报告任务（冲突也返回 400），统一按可重试处理。
        report_task_id = None
        deadline = time.monotonic() + settings.engine_wait_max
        while time.monotonic() < deadline:
            try:
                resp = bettafish_request(
                    "POST", "/api/report/generate", json_body={"query": query}
                )
                if resp.get("success"):
                    report_task_id = resp.get("task_id")
                    break
            except BettaFishError:
                pass  # 4xx（未就绪/冲突）或网络错误：等待后重试
            _sleep(settings.poll_interval)

        if not report_task_id:
            _fail(db, task, f"等待引擎产出超时（{settings.engine_wait_max}s）")
            return
        task.report_task_id = report_task_id
        task.status = "reporting"
        db.commit()

        # ---- 3. 轮询报告生成进度 ----
        # progress 对已清理任务会返回 completed 兜底，因此无需担心任务被基座裁剪
        report_status = None
        deadline = time.monotonic() + settings.report_wait_max
        while time.monotonic() < deadline:
            try:
                resp = bettafish_request("GET", f"/api/report/progress/{report_task_id}")
                report_status = resp.get("status")
            except BettaFishError:
                report_status = None
            if report_status in ("completed", "error"):
                break
            _sleep(settings.poll_interval)

        if report_status != "completed":
            _fail(db, task, f"报告生成未完成（status={report_status}）")
            return

        # ---- 4. 落报告索引 ----
        report = Report(
            task_id=task.id,
            title=query[:255],
            report_task_id=report_task_id,
        )
        db.add(report)
        task.status = "completed"
        task.error = None
        db.commit()
    finally:
        db.close()
