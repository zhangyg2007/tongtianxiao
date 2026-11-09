# LEGACY：M2 FastAPI 业务层（已归档）

## 这是什么

- 早期 M2 设计线的独立 FastAPI 服务：`server/app/main.py`
- 自带 SQLAlchemy 四表（`users` / `analysis_tasks` / `reports` / `config_audits`）、JWT、配置审计与轮询式任务基座
- 依赖 `bettafish-main` 基座的 HTTP 接口，默认访问 `http://localhost:5000`

## 为何废弃

- 与 B 线主线的运行时模型冲突：主线是 **Flask + Redis/RQ + 本地 PG `core`**，任务状态在 Redis + `core.task`，不是独立 FastAPI 进程 + 自己的四张表
- 两套任务状态、两套产物索引会直接把背调/舆情链路切碎
- 代码未删除，仅作为 M2 设计留档

## 替代方案

- 业务接口：`bettafish-main/backend/api/v1.py`（Flask Blueprint，`/api/v1/*`）
- 异步任务：`bettafish-main/backend/worker/`（RQ 双队列 `dd` / `pr`）
- 数据模型：`bettafish-main/backend/migrations/001_core_schema.sql`（`core` schema）
- 产品前端：`bettafish-main/frontend/`（React + Vite）

## 删除条件

同时满足才可删除：

1. B 线在服务器稳定运行 ≥ 30 天，且 `core.task` / `core.artifact` 已覆盖 M2 四表全部使用场景；
2. `archive/m2-20261104` 分支可随时取回（已推送远端）；
3. 全仓库无 `from server` / `server.app` 的运行时引用。

在此之前：**不参与构建、不安装依赖、不修 bug**。
