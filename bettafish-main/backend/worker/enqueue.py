"""任务提交/取消辅助函数（Flask API 侧调用）。

submit_task 流程：插 core.task(queued) → 按 product_line 入对应 RQ 队列，
job_id = task_id，两侧一一对应。
"""

import redis
from rq.exceptions import InvalidJobOperation

from . import config, store


def _queue(product_line: str) -> "rq.Queue":
    import rq

    conn = redis.Redis.from_url(config.REDIS_URL)
    name = config.QUEUE_DD if product_line == "dd" else config.QUEUE_PR
    return rq.Queue(name, connection=conn, default_timeout=config.JOB_TIMEOUT_SECONDS)


def submit_task(
    product_line: str,
    task_type: str,
    requested_by: int,
    input: dict | None = None,
    object_id: int | None = None,
    project_id: int | None = None,
    idempotency_key: str | None = None,
) -> str:
    """创建任务并入队，返回 task_id。

    幂等：带 idempotency_key 重复提交时返回已存在任务（唯一约束兜底）。
    """
    task_id = store.create_task(
        product_line=product_line,
        task_type=task_type,
        requested_by=requested_by,
        input=input,
        object_id=object_id,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )
    _queue(product_line).enqueue(
        "backend.worker.jobs.execute_task",
        task_id=task_id,
        job_id=task_id,
    )
    return task_id


def cancel_task(task_id: str) -> bool:
    """取消任务：RQ 侧 cancel（未开始的直接删；执行中的靠处理器检查）+
    core.task 置 canceled。返回是否至少一侧取消成功。"""
    ok = False
    try:
        job = _queue("dd").fetch_job(task_id) or _queue("pr").fetch_job(task_id)
        if job is not None:
            job.cancel()
            ok = True
    except InvalidJobOperation:
        pass
    before = store.get_task(task_id)
    store.mark_canceled(task_id)
    return ok or (before is not None and before["status"] != "canceled")
