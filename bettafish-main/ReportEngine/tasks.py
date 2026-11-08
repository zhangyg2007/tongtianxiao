"""RQ job：报告生成任务的执行体（在 RQ worker 进程内运行）。

链路：flask_interface /generate → RQ 'pr' 队列 → run_report_job
→ 复用 flask_interface.run_report_generation 的执行流程，
状态与事件写 Redis（task_store），Flask 侧 SSE 直接消费。

与 backend/worker 的关系：本模块是遗留报告路径的 job 函数；
后续 /api/v1 统一入口上线后，报告任务改经 backend.worker.jobs
注册表派发到这里（core.task/task_step 亦同步落 PG）。
"""

import threading

from loguru import logger

from . import task_store

# 执行线程 → task_id 映射，供 loguru 日志转发按任务归属分流
_task_by_thread: dict[int, str] = {}

_log_stream_handler_id: int | None = None

_EXCLUDED_ENGINE_PATH_KEYWORDS = ("ForumEngine", "InsightEngine", "MediaEngine", "QueryEngine")
_LOG_STREAM_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _stream_log_to_task(message):
    """把当前线程的 loguru 日志转发到该线程正在执行的任务事件流。"""
    try:
        task_id = _task_by_thread.get(threading.get_ident())
        if not task_id:
            return
        record = message.record
        level_name = record["level"].name
        if level_name not in _LOG_STREAM_LEVELS:
            return
        file_path = record["file"].path
        if any(keyword in file_path for keyword in _EXCLUDED_ENGINE_PATH_KEYWORDS):
            return

        timestamp = record["time"].strftime("%H:%M:%S.%f")[:-3]
        task_store.publish_event(
            task_id,
            "log",
            {
                "line": f"[{timestamp}] [{level_name}] {record['message']}",
                "level": level_name.lower(),
                "timestamp": timestamp,
                "message": record["message"],
                "module": record.get("module", ""),
                "function": record.get("function", ""),
            },
        )
    except Exception:
        # 日志钩子里不允许再抛异常，避免递归
        pass


def _setup_log_stream_forwarder():
    """worker 进程内挂一次 loguru 钩子。"""
    global _log_stream_handler_id
    if _log_stream_handler_id is not None:
        return
    _log_stream_handler_id = logger.add(
        _stream_log_to_task,
        level="DEBUG",
        enqueue=False,
        catch=True,
    )


def enqueue_report_job(task_id: str, query: str, custom_template: str = "") -> None:
    """把报告任务放入 RQ 'pr' 队列（Flask 侧调用）。"""
    import rq

    queue = rq.Queue("pr", connection=task_store.get_redis(), default_timeout=7200)
    queue.enqueue(
        "ReportEngine.tasks.run_report_job",
        task_id=task_id,
        query=query,
        custom_template=custom_template,
        job_id=f"report_{task_id}",
    )


def run_report_job(task_id: str, query: str, custom_template: str = "") -> dict:
    """RQ job 入口：绑定 task_id 执行报告生成。"""
    # 延迟导入避免与 flask_interface 循环引用
    from .flask_interface import ReportTask, run_report_generation

    _setup_log_stream_forwarder()

    if not task_store.exists(task_id):
        raise ValueError(f"task {task_id} 不存在于 Redis task_store")
    task = ReportTask(task_id)

    _task_by_thread[threading.get_ident()] = task_id
    try:
        logger.info(f"[task {task_id}] worker 开始执行报告生成: {query}")
        run_report_generation(task, query, custom_template)
        return {"task_id": task_id, "status": task.status}
    finally:
        _task_by_thread.pop(threading.get_ident(), None)
