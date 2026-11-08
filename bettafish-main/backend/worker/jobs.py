"""RQ job 入口与任务处理器注册表。

execute_task 是唯一的 RQ job 函数；按 core.task.task_type 派发到
注册的处理器。处理器通过 TaskContext 上报进度（写 core.task_step /
progress / stage），SSE 接口后续直接订阅这些表。

P0 阶段先注册 demo 处理器跑通链路；引擎接入时在 HANDLERS 注册：
    @register("investment_dd")
    def investment_dd(ctx: TaskContext, input: dict): ...
"""

import time
from contextlib import contextmanager

from loguru import logger

from . import store

HANDLERS: dict[str, "callable"] = {}


class TaskCanceled(Exception):
    """处理器主动取消（用户取消）。execute_task 据此落 canceled 而非 failed。"""


def register(task_type: str):
    def deco(fn):
        HANDLERS[task_type] = fn
        return fn
    return deco


class TaskContext:
    """处理器内可用的进度上报句柄。"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._seq = 0
        self._last_progress = 0

    def set_stage(self, stage: str, progress: int | None = None) -> None:
        if progress is not None:
            self._last_progress = progress
        store.set_progress(self.task_id, self._last_progress, stage)

    def set_progress(self, progress: int) -> None:
        self._last_progress = progress
        store.set_progress(self.task_id, progress)

    @contextmanager
    def step(self, name: str, detail: dict | None = None):
        """记录一个任务步骤：进入时插 running，退出时按异常与否收尾。"""
        self._seq += 1
        seq = self._seq
        store.append_step(self.task_id, seq, name, "running", detail)
        started = time.monotonic()
        try:
            yield
        except Exception as e:
            store.finish_step(self.task_id, seq, "failed",
                              {"error": str(e), "elapsed_ms": int((time.monotonic() - started) * 1000)})
            raise
        else:
            store.finish_step(self.task_id, seq, "succeeded",
                              {"elapsed_ms": int((time.monotonic() - started) * 1000)})


def execute_task(task_id: str) -> dict:
    """RQ job 入口（job_id == task_id）。加载 core.task 并派发执行。"""
    task = store.get_task(task_id)
    if task is None:
        raise ValueError(f"task {task_id} 不存在于 core.task")

    task_type = task["task_type"]
    handler = HANDLERS.get(task_type)
    if handler is None:
        store.mark_failed(task_id, "no_handler",
                          f"未注册的任务类型: {task_type}（已注册: {sorted(HANDLERS)}）")
        return {"ok": False, "reason": "no_handler"}

    import os
    import socket
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    store.mark_running(task_id, worker_id)

    ctx = TaskContext(task_id)
    input_dict = task["input"] or {}
    logger.info(f"[task {task_id}] 开始执行 {task_type}")
    try:
        result = handler(ctx, input_dict)
    except TaskCanceled as e:
        logger.info(f"[task {task_id}] {task_type} 已取消: {e}")
        store.mark_canceled(task_id)
        return {"ok": False, "reason": "canceled"}
    except Exception as e:
        logger.exception(f"[task {task_id}] {task_type} 执行失败")
        store.mark_failed(task_id, "handler_error", str(e))
        raise
    store.mark_succeeded(task_id, result if isinstance(result, dict) else {"result": result})
    logger.info(f"[task {task_id}] {task_type} 执行成功")
    return result


# ====== P0 demo 处理器：服务器上验证队列链路用 ======

@register("demo_pipeline")
def demo_pipeline(ctx: TaskContext, input: dict) -> dict:
    """三步演示：模拟抓取 → 解析 → 生成，每步 sleep 可配。"""
    wait = float(input.get("step_seconds", 2))
    with ctx.step("fetch_data"):
        ctx.set_stage("抓取数据", 10)
        time.sleep(wait)
    with ctx.step("parse_data"):
        ctx.set_stage("解析数据", 50)
        time.sleep(wait)
    with ctx.step("generate_report"):
        ctx.set_stage("生成报告", 90)
        time.sleep(wait)
    ctx.set_stage("完成", 100)
    return {"demo": True, "steps": 3, "echo": input}


# ====== 引擎接入：InsightEngine 深度研究（去 Streamlit 执行体） ======

@register("insight_research")
def insight_research(ctx: TaskContext, input: dict) -> dict:
    """舆情洞察深度研究。

    延迟导入 InsightEngine（sentence_transformers 等重依赖只在
    该类型任务真正执行时加载，不影响 worker 启动速度与其他任务）。
    input: {"query": str, "max_reflections"?: int, "output_dir"?: str}
    """
    from InsightEngine.runner import ResearchCanceled, run_research
    from InsightEngine.utils.config import Settings

    query = (input or {}).get("query", "").strip()
    if not query:
        raise ValueError("input.query 不能为空")

    overrides = {}
    if input.get("output_dir"):
        overrides["OUTPUT_DIR"] = input["output_dir"]
    if input.get("max_reflections"):
        overrides["MAX_REFLECTIONS"] = int(input["max_reflections"])
    config = Settings(**overrides) if overrides else None

    # 当前段落步骤的上下文管理器句柄（paragraph_start 进入 / paragraph_done 退出）
    current_step = None

    def _close_step():
        nonlocal current_step
        if current_step is not None:
            current_step.__exit__(None, None, None)
            current_step = None

    def on_progress(event: dict) -> None:
        etype = event.get("type")
        if etype == "paragraph_start":
            _close_step()
            current_step = ctx.step(
                f"段落{event['index'] + 1}/{event['total']}: {event['title']}",
                {"title": event["title"]},
            ).__enter__()
            ctx.set_stage(event.get("message", ""), event.get("progress"))
        elif etype == "paragraph_done":
            _close_step()
            ctx.set_progress(event.get("progress", 0))
        elif etype == "complete":
            _close_step()
            ctx.set_stage("完成", 100)
        else:
            message = event.get("message")
            if message:
                ctx.set_stage(message, event.get("progress"))

    def should_stop() -> bool:
        """段落边界检查 core.task 是否已被取消。"""
        try:
            task = store.get_task(ctx.task_id)
            return task is not None and task["status"] == "canceled"
        except Exception:
            return False

    try:
        result = run_research(
            query, config=config, on_progress=on_progress, should_stop=should_stop
        )
    except ResearchCanceled as e:
        _close_step()
        raise TaskCanceled(str(e))
    _close_step()

    # 精简结果：search_history 与段落全文不入 core.task.result（PG 侧只留摘要）
    slim = {k: v for k, v in result.items() if k != "search_history"}
    slim["paragraphs"] = [
        {k: v for k, v in p.items() if k != "latest_summary"}
        for p in result.get("paragraphs", [])
    ]
    return slim
