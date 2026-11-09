# Git 历史审计报告

> 审计对象：`d:\WORKSPACE\TraeWorkspace\bettafish-main`
> 审计日期：2026-11-09
> 审计方式：只读（`git remote -v` / `git status` / `git branch -a -vv` / `git stash list` / `git log` / `git show` / `git reflog` / `git ls-files` / `git ls-tree` / `git ls-remote` / `git grep` / `git check-ignore`）
> 未执行：任何写操作、commit、push、改 remote、切分支、stash、checkout、启动服务

---

## 一屏结论

| 问题 | 结论 |
|---|---|
| **仓库是否已统一到 `zhangyg2007/tongtianxiao`？** | ✅ **是**。`origin` 的 fetch/push 均为该地址；`git ls-remote --heads origin` 实测 GitHub 上 `refs/heads/main = 7e0c36e`，与本地 HEAD 完全一致 |
| **是否存在嵌套仓库 / 第二个 `.git`？** | ✅ **不存在**。全盘递归只找到外层一个 `.git`；`bettafish-main/bettafish-main/` 只是源码子目录，不是独立仓库 |
| **Redis + RQ 是哪次提交引入的？** | ✅ **`39f80ef`**（2026-11-08 20:37:42 +08:00，作者 `zhangyg2007`）。该提交引入 RQ 双队列骨架；**Redis 作为报告任务状态存储**是随后 `b56a317`（20:47:13） |
| **引入前任务管理是什么？** | ✅ 确认：`ReportEngine/flask_interface.py` 中的模块级全局变量 `current_task = None` + `task_lock = threading.Lock()`（另有 `stream_lock`、`tasks_registry`），单进程同时只能跑一个报告任务 |
| **当前代码是原始开源版还是已改造？** | ✅ **已改造，且是 P0 改造后的版本**。共 11 个提交，其中 8 个 P0 + 2 个 M2，不是 BettaFish 原始状态 |
| **当前技术栈与旧 155 人日文档的差异** | 主要 3 处：① 后端存在 Flask（主）+ FastAPI（`server/` 遗留，未接入）双体系；② 前端 React 工作台已建，但旧 `templates/index.html` 仍用 iframe 拉 3 个 Streamlit（8501–8503），双前端并存；③ 数据库 PG 新 schema 已建，但 MindSpider 采集侧仍是 MySQL，双库并存 |
| **仓库最严重的隐患** | ❌ `config.py`（根目录与 `backend/worker/config.py`）被上游 `.gitignore` 的 `config.py` 规则吞掉，**从未进入版本库**。新克隆缺少该文件，`app.py:154` 的 `from config import settings` 会直接失败；`rq` 也未写入 `requirements.txt`（仅存在于 `setup_venv.sh`） |
| **云服务器 `/opt/gitdownload/tongtianxiao`** | ⚠️ **未核实**。本次未连接服务器（此前多次 SSH 卡死），其 remote 指向无法确认 |

**一句话**：仓库归属已经统一，历史干净无改写痕迹；Redis+RQ 是 P0 阶段由仓库主人在 2026-11-08 晚集中引入的，不是第三方注入。真正要处理的不是"归属"，而是"漏提交配置 + 依赖声明不全 + 新旧两套体系并存"。

---

## 1. 仓库身份

### 1.1 实测事实

| 检查项 | 实测结果 | 判定 |
|---|---|---|
| Git 仓库根 | `D:/WORKSPACE/TraeWorkspace/bettafish-main`（外层） | ✅ |
| 嵌套 `.git` | 递归扫描仅 `D:\WORKSPACE\TraeWorkspace\bettafish-main\.git` 一个目录，无 `.git` 文件型子模块 | ✅ 无嵌套仓库 |
| 目录关系 | 外层 = 仓库根 + 业务壳（`server/`、`web/`、`wxapp/`、`.trae/`、`README.md`）；内层 `bettafish-main/` = BettaFish 源码（`app.py`、四引擎、`backend/`、`frontend/`、`templates/`） | ✅ 内层不是仓库 |
| `bettafish-v1.0.0.bak/` | 磁盘上存在，但 `git ls-files "bettafish-v1.0.0.bak/*"` = **0 个文件** | 本地备份，未入库 |
| `git remote -v` | `origin https://github.com/zhangyg2007/tongtianxiao.git`（fetch / push 各一条） | ✅ 等于指定仓库 |
| 其他 remote | 只有 `origin`，无 `upstream` / 其他镜像 | ✅ |
| GitHub 端实读 | `git ls-remote --heads origin` → `7e0c36ef... refs/heads/main` | ✅ 远端仓库真实存在且指向正确项目 |
| 本地 HEAD | `7e0c36ef33ecc4914df36fa5361831110184aec8` | — |
| 远端跟踪 HEAD | `origin/main = 7e0c36ef33ecc4914df36fa5361831110184aec8` | ✅ **两者一致** |
| 分支 | 仅 `main`，跟踪 `origin/main`；`remotes/origin/main` 同一 sha；无其他本地/远端分支 | ✅ |
| stash | `git stash list` 为空 | ✅ 无 stash |
| worktree | 仅一个：`D:/WORKSPACE/TraeWorkspace/bettafish-main  7e0c36e [main]` | ✅ |
| 已跟踪文件数 | 588 | — |
| 文件分布 | `bettafish-main/` 493、`bettafish-main` 引号路径 39（含中文文档名）、`web/` 23、`server/` 18、`wxapp/` 6、`.trae/` 6 | — |
| `server` 端 remote | `/opt/gitdownload/tongtianxiao`（用户提供路径） | ⚠️ **未核实**（服务器不可达，未连接） |

### 1.2 未提交改动

| 类型 | 文件 | 说明 |
|---|---|---|
| 已修改（5） | [app.py](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/app.py)、[pipeline.py](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/dd/pipeline.py)、[report.py](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/dd/report.py)、[template.py](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/dd/template.py)、[jobs.py](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/worker/jobs.py) | `+189 / −33` |
| 新增未跟踪（代码） | `backend/dd/writer.py`、`backend/sources/`（`juchao.py` / `akshare_src.py` / `tianyancha.py` / `case_file.py` / `base.py`）、`backend/worker/entities.py`、`tests/test_sources.py` | 最小可用改造集产物 |
| 新增未跟踪（文档） | `.trae/documents/cases/`、`.trae/documents/prompts/`、`多Agent协作Prompt工程方案.md`、`改造模块清单.md` | 设计与试跑资料 |

> **来源说明（重要）**：上述改动不是来历不明的第三方修改，而是本次会话链条中「最小可用改造集」的产物——配置外部化、`backend/sources/` 数据源适配层、实体对齐（USCC `natural_key`）、LLM 章节写作、veto 关键词误伤修复与 loguru 依赖修复。当前**尚未提交**，需由用户决定提交策略。审计期间未对其做任何修改。

---

## 2. 提交历史时间线

共 **11 个提交**（< 50，无需拆分附录），全部为线性历史，无 merge，无 tag。时间正序：

| # | 日期（+08:00） | commit | 作者 | 提交信息 | 改动范围 | 类别 |
|---|---|---|---|---|---|---|
| 1 | 2026-11-02 14:03:04 | `000bf5b` | zhangyg2007 | feat: 基于 BettaFish v3.0.0 的定制项目初始提交 | 520 files，+1,673,120 | 初始化 |
| 2 | 2026-11-04 16:13:10 | `86b960b` | zhangyg2007 | feat(M2): 业务层 FastAPI 骨架 | 17 files，+675 | 功能 |
| 3 | 2026-11-04 16:26:59 | `3e035f7` | zhangyg2007 | feat(M2): 任务管线闭环——报告任务回填与索引落库 | 6 files，+201/−23 | 功能 |
| 4 | 2026-11-08 20:08:11 | `f918e4d` | zhangyg2007 | docs(P0): 部署与实施规划落地 Ubuntu 服务器方案 | 7 files，+3,616（含 `001_core_schema.sql` 191 行） | 文档 |
| 5 | 2026-11-08 20:34:19 | `2fdb08a` | zhangyg2007 | chore(P0): 部署规格确认 24.04 x64，安装步骤固化为一键脚本 | 4 files，+108/−17 | 部署配置 |
| 6 | 2026-11-08 20:37:42 | `39f80ef` | zhangyg2007 | feat(P0): RQ worker 骨架——dd/pr 双队列、15s 心跳、60s 僵死扫描 | 8 files，+503/−3 | 功能 |
| 7 | 2026-11-08 20:47:13 | `b56a317` | zhangyg2007 | feat(P0): ReportEngine 去单例——任务状态迁 Redis、执行迁 RQ、SSE 消费 Redis Stream | 6 files，+522/−383 | 重构 |
| 8 | 2026-11-08 22:03:11 | `0491469` | zhangyg2007 | feat(P0): InsightEngine 执行体抽离 Streamlit——runner + on_progress 回调，接入 RQ 处理器注册表 | 4 files，+302/−63 | 重构 |
| 9 | 2026-11-08 22:05:12 | `d5fda75` | zhangyg2007 | feat(P0): /api/v1 统一接口——任务/对象/产物 CRUD + SSE 结构化进度 | 5 files，+412 | 功能 |
| 10 | 2026-11-08 22:12:34 | `98b20a5` | zhangyg2007 | feat(P0): React 前端工作台——案卷列表/任务详情 SSE/证据抽屉 + /api/v1 证据接口 | 25 files，+1,621/−13 | 功能 |
| 11 | 2026-11-08 22:18:56 | `7e0c36e` | zhangyg2007 | feat(P0): 投资尽调 12 章模板 + 评分卡三态 + 证据后校验（investment_dd） | 11 files，+859/−3 | 功能 |

### 里程碑聚合

| 阶段 | 提交 | 实际内容 |
|---|---|---|
| **M1/M2 骨架（11-02 ~ 11-04）** | 1–3 | 导入 BettaFish v3.0.0 全量；在 `server/` 建 FastAPI 业务层（JWT、users/analysis_tasks/reports/config_audits 四表）与任务管线 |
| **P0 规划与基建（11-08 20:08 ~ 20:37）** | 4–6 | 部署文档 + core schema 9 表 + 三个部署脚本 + RQ worker 骨架 |
| **P0 主干改造（11-08 20:47 ~ 22:18）** | 7–11 | 去单例 / Redis 状态与 SSE / Insight 执行体抽离 / `/api/v1` / React 工作台 / 12 章模板与证据校验 |

### 提交节奏观察

- 11-02 → 11-04 间隔 2 天；11-04 → 11-08 间隔 4 天；11-08 当晚 20:08–22:18 连续 8 个提交，间隔 2–13 分钟。
- 全部时间戳为 `+08:00`，无跨时区异常。
- 无重复提交信息（`git log --format=%s | Group-Object` 无重复项）。

---

## 3. Redis + RQ 的引入（重点）

### 3.1 精确定位

| 字段 | 值 |
|---|---|
| **首次引入 RQ 的提交** | `39f80efd612e09f1796473e5f5cf8e3bcda49002`（短 sha `39f80ef`） |
| 作者 | `zhangyg2007` <`zhangyg***@163.com`>（本地部分为 `zhangyg2007`） |
| 作者邮箱判断依据 | 11 个提交的 `%ae` 全部相同；与 GitHub 账号 `zhangyg2007` 同名 |
| 提交者（committer） | `zhangyg2007` <`zhangyg***@163.com`>（与本提交作者一致） |
| 提交日期 | `2026-11-08T20:37:42+08:00` |
| 改动规模 | 8 files changed, **+503 / −3** |
| **首个使用 Redis 存任务状态的提交** | `b56a317d0014db73157d6fe417997c47f3b7a00f`，2026-11-08T20:47:13+08:00，+522/−383 |

**注意区分**：`redis` 这个词在初始提交里就出现过，但那是 **MindSpider 内置 MediaCrawler 的可选缓存后端**（`cache/redis_cache.py`、`cache/cache_factory.py:36`），与任务队列无关。作为**任务队列与任务状态存储**的 Redis，是 11-08 这两个提交引入的。

### 3.2 `39f80ef` 完整 message（含 body）

```text
feat(P0): RQ worker 骨架——dd/pr 双队列、15s 心跳、60s 僵死扫描

backend/worker/：
- store.py     core.task/task_step 的 PG 读写（job_id==task_id 一一对应）
- jobs.py      execute_task 入口 + 处理器注册表 + demo_pipeline 自检处理器
- worker.py    HeartbeatWorker：job 执行期间独立线程写 heartbeat_at
- scheduler.py APScheduler 每 60s 收割心跳超 2min 的僵死任务
- enqueue.py   submit_task/cancel_task（Flask API 侧调用）

setup_venv.sh 增补 apscheduler；部署文档 §4 补启动命令与链路自检步骤。
```

### 3.3 该提交的文件与增删行

| 文件 | 增 | 删 |
|---|---:|---:|
| `.trae/documents/P0-Ubuntu服务器部署与实施规划.md` | 18 | 2 |
| `bettafish-main/backend/scripts/setup_venv.sh` | 1 | 1 |
| `bettafish-main/backend/worker/__init__.py` | 14 | 0 |
| `bettafish-main/backend/worker/enqueue.py` | 64 | 0 |
| `bettafish-main/backend/worker/jobs.py` | 112 | 0 |
| `bettafish-main/backend/worker/scheduler.py` | 37 | 0 |
| `bettafish-main/backend/worker/store.py` | 190 | 0 |
| `bettafish-main/backend/worker/worker.py` | 67 | 0 |

关键代码（`39f80ef:bettafish-main/backend/worker/enqueue.py`）：

```python
import redis
from rq.exceptions import InvalidJobOperation
from . import config, store

def _queue(product_line: str) -> "rq.Queue":
    import rq
    conn = redis.Redis.from_url(config.REDIS_URL)
    name = config.QUEUE_DD if product_line == "dd" else config.QUEUE_PR
    return rq.Queue(name, connection=conn, default_timeout=config.JOB_TIMEOUT_SECONDS)
```

> ⚠️ 该文件 `from . import config`，但 `backend/worker/config.py` 当时就**不在提交内**（见 §5.2）。首次克隆会 `ImportError`。

### 3.4 引入之前的任务管理方式（已核实）

在 `000bf5b:bettafish-main/ReportEngine/flask_interface.py` 中：

```python
report_agent = None
current_task = None
task_lock = threading.Lock()
STREAM_TERMINAL_STATUSES = {"completed", "error", "cancelled"}
stream_lock = threading.Lock()
stream_subscribers = defaultdict(list)
```

并有 `tasks_registry` 作为历史任务表、`/generate` 用 `threading.Thread(target=...)` 启动、`/task/status` 在 `with task_lock:` 下读取 `current_task`。**结论：确为模块级全局变量 + `threading.Lock`，同一时刻只允许一个报告任务**。✅

### 3.5 前后配套提交

| 关系 | 提交 | 配套内容 |
|---|---|---|
| 前置 | `f918e4d`（20:08） | 部署文档首次写入 Redis/RQ 方案；新增 `backend/migrations/001_core_schema.sql`（9 张 core 表） |
| 前置 | `2fdb08a`（20:34） | 新增 `install_env.sh` / `init_db.sh` / `setup_venv.sh`；`setup_venv.sh` 内声明 `"redis>=4.6" rq`，即 RQ 依赖在此落地 |
| 本体 | `39f80ef`（20:37） | RQ 双队列 + 心跳 + 僵死扫描；脚本追加 `apscheduler` |
| 后续 | `b56a317`（20:47） | ReportEngine 去单例；新增 `ReportEngine/task_store.py`（Redis Hash + Stream）与 `ReportEngine/tasks.py`（RQ job）；`setup_venv.sh` 再补 `openai json-repair pydantic-settings matplotlib scipy wordcloud weasyprint`，`install_env.sh` 补 WeasyPrint 系统库 |
| 后续 | `0491469` / `d5fda75` | Insight runner 与 `/api/v1` 接入 RQ 处理器注册表 |

**依赖声明现状**：`rq` 只写在 [setup_venv.sh](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/scripts/setup_venv.sh#L22-L23)，**根 `requirements.txt` 没有 `rq`**；`redis>=4.6.0` 在 [requirements.txt](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/requirements.txt#L38) 第 38 行。用 `pip install -r requirements.txt` 建的环境跑不了 RQ。❌

### 3.6 来源判断：原作者还是第三方/自动化？

| 维度 | 证据 | 判断 |
|---|---|---|
| 作者身份 | 11 个提交作者均为 `zhangyg2007 <zhangyg***@163.com>` | **原作者本人**，无第三方身份 |
| 提交者身份 | 仅初始提交 `000bf5b` 的 committer 是 `trae-solo-agent <solo-agent@trae.ai>`；其余 10 个（含 `39f80ef`、`b56a317`）committer 均为 `zhangyg2007` | 初始导入由 AI Agent 代提交；RQ 提交由本人署名提交 |
| 提交风格 | `39f80ef` 使用结构化 bullet、明确列出文件名与职责、精确到 15s/60s/2min 阈值，与相邻 P0 提交风格完全一致 | 非孤立/异常提交，属同一工作流 |
| 时间分布 | 20:08→20:34→20:37→20:47→22:03→22:05→22:12→22:18，连续两条流水型提交 | 正常开发节奏，无"补录/伪造"特征 |
| 单次体量 | +503/−3，无巨型二进制、无批量删除 | 正常 |

**结论**：`39f80ef` 不是第三方注入，也不是独立自动化脚本提交，而是仓库主人（在 AI 辅助下）于 P0 阶段连续改造的一环。

### 3.7 历史改写痕迹

| 检查 | 结果 |
|---|---|
| `git reflog` | 11 条，全部是 `commit:`，无 `reset` / `rebase` / `amend` / `checkout -B` |
| 提交顺序 | `git log --reverse` 与 reflog 顺序一致，sha 首尾相接 |
| 重复提交 | 无 |
| 时间倒序/未来时间 | 无，全部 `+08:00` 且单调递增 |
| merge / tag | 无 merge，`git tag` 为空 |
| **远端是否被 force-push** | ⚠️ **本地无法证明**。本地 reflog 只记录本机操作；远端强推需 GitHub audit log / events API 才能确认。当前本地无任何改写迹象 |

---

## 4. 当前实际技术栈盘点

以代码事实为准（HEAD `7e0c36e` + 工作区）。旧文档指《前端与产品形态升级设计》v1.0（155 人日版，现文档已修订为 v1.1 / 141 人日）。

| 层面 | 当前实现 | 证据（文件:行号） | 与旧文档是否一致 |
|---|---|---|---|
| **任务队列** | RQ，双队列 `dd`（背调）/ `pr`（舆情），job_id == task_id | [enqueue.py:13-18](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/worker/enqueue.py#L13-L18)、[tasks.py:74-78](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/tasks.py#L74-L78)、[worker.py:52](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/worker/worker.py#L52) | ✅ 一致（文档 P0 第 1 项：Redis + RQ worker 骨架） |
| **报告任务状态管理** | Redis Hash（任务字段）+ Redis Stream（事件流，`XADD`/`XREAD BLOCK`，TTL 7 天）；`ReportTask` 为写穿门面 | [task_store.py:29-34](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/task_store.py#L29-L34)、[:64](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/task_store.py#L64)、[:98](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/task_store.py#L98)；[flask_interface.py:10-11](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/flask_interface.py#L10-L11) 注明已删除 `current_task`/`task_lock` | ✅ 一致（去单例完成） |
| **后端 Web** | **Flask** 主服务：`app.py` 注册 `report_bp` 与 `/api/v1`；另有 `server/` 下 **FastAPI**（M2 遗留，独立 `uvicorn`，未挂到主站） | [app.py:19](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/app.py#L19)、[:80](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/app.py#L80)、[:85-88](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/app.py#L85-L88)；[flask_interface.py:29](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/flask_interface.py#L29)；[server/app/main.py:6,12](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/server/app/main.py#L6-L12) | ⚠️ **部分不一致**：旧文档只规划 Flask + `/api/v1`，实际多出一套未接入的 FastAPI 业务层 |
| **前端** | **React 18.3 + TypeScript 5.6 + Vite 5.4**（`frontend/`，20 个跟踪文件，案卷列表/详情/SSE/证据抽屉）；同时旧 `templates/index.html` 仍用 iframe 拉 Streamlit 三页 | `frontend/package.json`（react/react-dom `^18.3.1`、vite `^5.4.10`）；[index.html:2280-2282](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/templates/index.html#L2280-L2282)、[:3342](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/templates/index.html#L3342)（8501 insight / 8502 media / 8503 query） | ⚠️ **部分不一致**：文档要求 React 替换 Streamlit，实际双前端并存，旧入口未下线 |
| **数据库** | 主链路 **PostgreSQL**：`core` schema 9 张表（object / object_alias / task / task_step / evidence / artifact / artifact_block / artifact_citation / artifact_anchor），`psycopg2` 直连；采集侧 **MySQL**（`pymysql`/`aiomysql`） | [001_core_schema.sql:23-185](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/migrations/001_core_schema.sql#L23-L185)；[store.py:1](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/worker/store.py#L1)；`MindSpider/main.py:15`、`utils/db/database_manager.py:44` | ⚠️ **部分不一致**：业务库已 PG，采集库仍 MySQL，双库未统一 |
| **向量检索** | 本地 `sentence_transformers` 编码（`InsightEngine/agent.py:14`），**无向量数据库**（全仓无 pgvector / Milvus / Chroma / FAISS 引用） | [InsightEngine/agent.py:14](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/InsightEngine/agent.py#L14) | ✅ 一致（旧文档 P0 未把向量库列入交付） |
| **缓存** | **Redis**（任务状态/事件流）；MediaCrawler 另有可选 `RedisCache` 后端 | [task_store.py:29](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/ReportEngine/task_store.py#L29)；`MindSpider/.../cache/cache_factory.py:36` | ✅ 一致 |
| **LLM 客户端** | 统一 **OpenAI 兼容**客户端，多厂商可配（Kimi / Gemini 中转 / DeepSeek，各有 KEY/BASE_URL/MODEL） | [QueryEngine/llms/base.py:55](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/QueryEngine/llms/base.py#L55)、[config.py:44-60](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/config.py#L44-L60)、`ForumEngine/llm_host.py:48`、`backend/dd/writer.py:46-48` | ✅ 一致（文档假设复用现有 LLM 封装） |
| **爬虫/采集** | `MindSpider` + 内置 MediaCrawler（Playwright，微博/小红书/抖音等）；新增 `backend/sources/` 适配层（巨潮、AkShare、天眼查、case_file → evidence） | `requirements.txt`（playwright 1.45）；`backend/sources/{juchao,akshare_src,tianyancha,case_file}.py`（**未跟踪**） | ⚠️ **已实现未入库**：文档 P0 数据源为 AkShare + 巨潮 + 天眼查 + Tavily，代码已写但未提交 |
| **配置管理** | `pydantic-settings` + `.env` + `settings` 代理（`__getattr__` 转发、`reload_settings()` 原地热替换） | [config.py:22](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/config.py#L22)、[config.py 尾部 `_SettingsProxy` / `reload_settings`](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/config.py)；`app.py:154,239,1614` 调用 | ✅ 选型一致，但 ❌ **文件未纳入版本控制**（见 §5.2） |
| **部署方式** | **Ubuntu 24.04 + apt 装 PG/Redis + venv + 3 个 shell 脚本**（`install_env.sh` / `init_db.sh` / `setup_venv.sh`），配部署文档；仓库同时残留 Docker 物（`Dockerfile`、`docker-compose.yml`、`deploy/docker-compose.m1.yml`） | [backend/scripts/](file:///d:/WORKSPACE/TraeWorkspace/bettafish-main/bettafish-main/backend/scripts) 3 个脚本；`bettafish-main/Dockerfile`、`docker-compose.yml`、`deploy/docker-compose.m1.yml` | ⚠️ **部分不一致**：文档定的 apt 方案已落地，但 M1 的 Docker 方案未清理 |

### 不一致项的具体差异

1. **双后端**：`server/app/main.py` 是 M2 阶段独立 FastAPI（JWT、四表、任务管线），与主站 Flask 无任何挂载关系；`app.py` 也不引用它。旧文档未规划该层，它属于历史遗留资产。
2. **双前端**：React 工作台（`frontend/`）与旧 `templates/index.html`（6071 行，iframe 拉 8501/8502/8503）并存；文档 P0 要求"新前端替换旧入口"，目前只完成新增，未下线旧入口。
3. **双数据库**：业务链走 PG `core` schema，采集链（MindSpider）仍走 MySQL `pymysql`；文档目标是统一 PG。
4. **配置未入库**：选型正确（pydantic-settings），但 `config.py` 被 `.gitignore` 忽略，版本库中不存在该文件——这是"实现一致、交付不一致"。
5. **依赖声明不完整**：`rq` 未写入 `requirements.txt`，只在部署脚本里；用全量 requirements 复现环境会缺包。

---

## 5. 结论与建议

### 5.1 当前代码处在什么状态

- **是已改造版本，不是原始开源版**。11 个提交中，`86b960b`/`3e035f7` 是 M2 业务层尝试，`f918e4d`→`7e0c36e` 是完整的一轮 P0 改造（8 个提交），覆盖了旧文档 P0 清单的全部 9 项：
  1. Redis + RQ worker 骨架 ✅
  2. `core.object/task/evidence/artifact` 建表 ✅（9 表）
  3. ReportEngine 去单例 ✅
  4. InsightEngine 执行体抽离 ✅
  5. SSE 结构化进度 ✅
  6. `/api/v1` 任务/对象/产物 ✅
  7. React 案卷列表/详情/证据抽屉 ✅
  8. 投资尽调 12 章模板 ✅
  9. 证据后校验（角标存在性 + 对象一致性）✅
- **改造程度**：P0 骨架完整、分层清晰（`backend/api`、`backend/worker`、`backend/dd`、`backend/sources`、`ReportEngine/task_store|tasks`），但**数据源层与 LLM 写作层尚未提交**，属于"工作区里有、仓库里没有"。
- **能不能跑**：
  - 本地工作区：此前回归 50/50 通过，端到端冒烟 9 章有数据、覆盖率 100%（历史记录，本次未重跑）。
  - **新克隆：不能直接跑**。缺 `config.py`（`app.py:154` `from config import settings` 失败）、缺 `backend/worker/config.py`（RQ worker 导入失败）、`requirements.txt` 缺 `rq`。

### 5.2 "统一仓库"诉求的具体建议

现状是**归属已统一，交付不完整**。建议按以下顺序处理（均为写操作，需用户授权后另开任务执行）：

| 步骤 | 动作 | 理由 | 风险 |
|---|---|---|---|
| 1 | 在服务器执行 `git remote -v` 与 `git log -1`，确认 `/opt/gitdownload/tongtianxiao` 指向同一地址与同一 sha | 目前唯一未核实项 | ⚠️ 服务器不可达，需等恢复；若它是独立克隆，可能落后或有本地改动 |
| 2 | 修 `.gitignore`：加 `!bettafish-main/config.py`、`!bettafish-main/backend/worker/config.py`（或改为提交 `config.example.py`） | 解决新克隆无法启动 | 若配置文件未来写入真实 key，会泄密；建议先脱敏或改 example 方案 |
| 3 | 把 `rq` 写入 `requirements.txt`，与 `setup_venv.sh` 对齐 | 依赖可复现 | 无 |
| 4 | 将当前 15 个文件拆 3 个提交入库：① 配置外部化 ② `backend/sources/` + 实体对齐 ③ LLM 写作 + 模板/veto 修复 | 避免工作区成果丢失 | 提交前需确认 `backend/sources/` 无硬编码密钥 |
| 5 | 决定 M2 遗留资产去留：`server/`（FastAPI）、`web/`（Vue）、`wxapp/` | 消除双后端/双前端困惑 | 删除会丢历史；建议打 tag 归档后移入 `legacy/` 或单独分支 |
| 6 | 视需要打 `v0.1-p0` tag，并在 README 标注当前真实入口（Flask + React） | 固化里程碑 | 无 |

**需要用户决策的点**：

1. `config.py` 是"提交脱敏版"还是"提交 `config.example.py` + 忽略真实文件"？后者更安全，但需改启动逻辑或文档。
2. `server/`、`web/`、`wxapp/` 是保留、归档还是删除？
3. 15 个未提交文件是否按建议拆 3 个 commit，还是合成 1 个？
4. 是否需要清理初始提交中的上游冗余（`MindSpider/` 235 个文件、`SentimentAnalysisModel/` 61 个文件）？清理需重写历史，代价高，非必要不建议。

### 5.3 已核实 / 未核实清单

**✅ 已核实（有命令输出或代码行号为证）**

- remote 指向 `zhangyg2007/tongtianxiao`，且 GitHub 端 `refs/heads/main` 与本地 HEAD 同为 `7e0c36e`
- 无嵌套 `.git`，外层为唯一仓库根
- 无其他分支、无 stash、单 worktree
- 11 个提交的完整 sha/作者/邮箱/时间/信息/改动量
- Redis + RQ 由 `39f80ef` 引入；Redis 任务状态由 `b56a317` 引入
- 引入前为 `current_task` 全局变量 + `task_lock` 线程锁
- 全部提交作者同一人；初始提交 committer 为 `trae-solo-agent`
- 本地 reflog 无 reset/rebase/amend 痕迹，无重复提交、无 merge、无 tag
- 12 项技术栈均定位到具体文件与行号
- `config.py` 与 `backend/worker/config.py` 未入版本库（`.gitignore:298`）
- `requirements.txt` 缺 `rq`

**⚠️ 未核实（无法从本地证明）**

- 服务器 `/opt/gitdownload/tongtianxiao` 的 remote 与 HEAD（服务器不可达）
- GitHub 远端历史上是否发生过 force-push（需 GitHub audit log / events API）
- `core` schema 9 表是否已在目标 PG 实际建表（本次未连库）
- 当前工作区端到端可跑性（本次为只读审计，未重跑测试与服务）
- 旧文档 v1.0（155 人日）的 P1/P2/P3 明细：现有文档已修订为 v1.1（141 人日，P0 39 / P1 37 / P2 29 / P3 36），155 版仅作为历史口径引用

---

## 附录：审计命令清单

```text
git rev-parse --show-toplevel
git remote -v
git ls-remote --heads origin
git status --short / --porcelain / --ignored
git branch -a -vv
git stash list
git worktree list
git rev-list --count HEAD
git log --format="%H|%an|%ae|%ad|%cn|%ce|%cd|%s" --date=iso-strict --reverse
git log --oneline --reverse -S"redis" / -S"from rq" / -S"Redis"
git log --format="%h %s" --shortstat
git show --stat --numstat --format=... <sha>
git show <sha>:<path>
git reflog --date=iso
git ls-files / git ls-tree -r --name-only
git check-ignore -v <path>
git grep -n <pattern> <rev>
```
