"""定时任务调度入口（APScheduler）。

启动（代码目录 bettafish-main/ 下）：
    ../.venv/bin/python -m backend.worker.scheduler

P0 只有一个定时任务：僵死任务扫描（每 60s）。
P3 预警接入后，2h 级轮询任务也注册到这里（设计文档 §0.1 决策③）。
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from . import config, store


def main() -> None:
    sched = BlockingScheduler(timezone="Asia/Shanghai")
    sched.add_job(
        store.reap_zombies,
        trigger="interval",
        seconds=config.REAP_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
        id="reap_zombies",
    )
    logger.info(
        f"调度器启动：僵死扫描每 {config.REAP_INTERVAL_SECONDS}s，"
        f"阈值 {config.ZOMBIE_THRESHOLD_SECONDS}s"
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器退出")


if __name__ == "__main__":
    main()
