"""P0 任务队列骨架：RQ 双队列（dd/pr）+ PG 任务状态 + 心跳僵死检测。

模块布局：
- config    环境配置（.env / 默认值）
- store     core.task / core.task_step 的 PG 读写
- jobs      RQ job 入口 execute_task 与任务处理器注册表
- enqueue   提交/取消任务的辅助函数（Flask API 侧调用）
- worker    RQ Worker 子类（带心跳线程）+ 启动入口
- scheduler 僵死任务扫描（APScheduler）+ 启动入口

运行方式（服务器上，代码目录 = bettafish-main/）：
    ../.venv/bin/python -m backend.worker.worker            # 任务执行进程
    ../.venv/bin/python -m backend.worker.scheduler        # 僵死扫描进程
"""
