"""RQ Worker 子类 + 启动入口（带任务级心跳线程）。

启动（代码目录 bettafish-main/ 下）：
    ../.venv/bin/python -m backend.worker.worker

行为：
- 监听 dd / pr 双队列（rq worker dd pr）；
- 每个 job 执行期间，独立线程每 15s 写 core.task.heartbeat_at；
- job 结束（无论成败）心跳线程随之退出；
- worker_id = hostname:pid 写入 core.task，便于排障。
"""

import threading

import redis
from loguru import logger
from rq import Worker

from . import config, store


class HeartbeatWorker(Worker):
    """在执行每个 job 期间，为对应 core.task 维持心跳。"""

    def perform_job(self, job, queue, *args, **kwargs):
        task_id = job.id  # 约定 job_id == task_id
        stop = threading.Event()
        hb = threading.Thread(
            target=self._heartbeat_loop, args=(task_id, stop), daemon=True
        )
        hb.start()
        try:
            return super().perform_job(job, queue, *args, **kwargs)
        finally:
            stop.set()
            hb.join(timeout=3)

    @staticmethod
    def _heartbeat_loop(task_id: str, stop: threading.Event) -> None:
        while not stop.wait(config.HEARTBEAT_INTERVAL_SECONDS):
            try:
                store.heartbeat(task_id)
            except Exception:
                # 心跳写库失败不中断任务本身，等下一轮
                logger.exception(f"心跳写入失败 task={task_id}")


def main() -> None:
    import os
    import socket

    conn = redis.Redis.from_url(config.REDIS_URL)
    # 触发注册表加载（execute_task 及 demo 处理器）
    from . import jobs  # noqa: F401

    worker = HeartbeatWorker(
        config.QUEUES,
        connection=conn,
        name=f"bettafish@{socket.gethostname()}:{os.getpid()}",
        default_worker_ttl=60,
    )
    logger.info(f"RQ worker 启动，队列: {config.QUEUES}, redis: {config.REDIS_URL}")
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
