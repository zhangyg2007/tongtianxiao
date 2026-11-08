# P0 Ubuntu 服务器部署与实施规划

> 版本：v1.0（部署规划，待服务器实测）
> 前置文档：[前端与产品形态升级设计.md](./前端与产品形态升级设计.md)（P0 计划见其 §6.1）
> 编制日期：2026-11-08
> 目标环境：公司 Ubuntu 服务器（具体版本待确认，本文按 22.04 / 24.04 LTS 双轨给出）
> 开发模式：工作站安装 Trae → SSH 连接服务器 → 在服务器上克隆仓库远程开发

---

## 0. 核心结论

1. **Ubuntu 是比 Windows 顺得多的目标环境**：PG 和 Redis 都是 apt 直装，Windows 上的 Memurai/WSL2 选型问题直接消失。
2. **Python 必须用 3.10/3.11，不能用 3.12+**：遗留代码钉死的 2023 年包（Pillow 9.5.0、streamlit 1.28.1、eventlet 0.33.3、pydantic 2.5.2）没有 cp312/cp313 预编译 wheel。已实测：Python 3.13 上装 Pillow 9.5.0 直接构建失败。
3. **P0 代码先行，服务器到位后半天内完成环境安装**：所有基础设施步骤已收敛为本文 §2 的一条命令块 + §3 的初始化验证。

---

## 1. 版本与组件选型

| 组件 | 选型 | 安装方式 | 依据 |
|---|---|---|---|
| 操作系统 | Ubuntu **24.04 LTS** 优先（22.04 亦可） | — | 24.04 的 apt 源带 PG16 + Redis 7；22.04 是 PG14 + Redis 6.0，P0 均够用 |
| Python | **3.11**（3.10 亦可） | 24.04 需 deadsnakes PPA；22.04 自带 3.10 | 遗留钉死包的安全区间是 ≤3.11（Pillow 9.5.0 最高提供 cp311 wheel） |
| PostgreSQL | 16（24.04）/ 14（22.04） | `apt install postgresql` | DDL 用到的 `gen_random_uuid()` 需 PG13+，两者均满足 |
| Redis | 7.x（24.04）/ 6.0（22.04） | `apt install redis-server` | RQ 依赖，apt 装完即系统服务，开机自启 |
| Node.js | 20 LTS | NodeSource | 仅前端构建期需要（React18+Vite+AntD5） |
| 仓库 | github.com/zhangyg2007/tongtianxiao（main） | git clone | 即当前仓库 |

**不需要**：Docker、conda、Memurai、WSL2。

---

## 2. 安装步骤（服务器上执行）

```bash
# 0. 基础工具
sudo apt update && sudo apt install -y git build-essential

# 1. PostgreSQL + Redis（一条命令）
sudo apt install -y postgresql redis-server

# 2. Python 3.11
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev
# 22.04 可直接用自带的 python3.10：sudo apt install -y python3.10-venv

# 3. Node 20（前端构建）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 4. 克隆仓库
git clone https://github.com/zhangyg2007/tongtianxiao.git ~/tongtianxiao
```

> 注：`requirements.txt` 含 torch（CPU 版约 200MB+），全量安装较慢。P0 骨架阶段可先建精简依赖（flask/rq/redis/psycopg/asyncpg/loguru/pydantic），跑通链路后再补全量。

---

## 3. 初始化与验证（P0 检查点）

```bash
# 1. 建库（PG 装完自动起服务；如未起：sudo systemctl start postgresql）
sudo -u postgres createuser --createdb $USER
createdb bettafish
psql -d bettafish -f bettafish-main/backend/migrations/001_core_schema.sql
psql -d bettafish -c "\dt core.*"   # 预期：9 张表（object/object_alias/task/task_step/evidence/artifact/artifact_block/artifact_citation/artifact_anchor）

# 2. Redis 验证
redis-cli ping                    # 预期：PONG
systemctl status redis-server     # 预期：active (running)

# 3. Python venv + 精简依赖
python3.11 -m venv ~/venv-p0
source ~/venv-p0/bin/activate
pip install flask rq "redis>=4.6" psycopg2-binary asyncpg loguru pydantic
```

三个命令块全部通过 = 基础设施就绪，P0 编码部分（RQ worker、去单例、SSE、/api/v1）即可在 Trae SSH 会话里开发调试。

---

## 4. P0 服务器上的运行形态（开发期）

开发期不写 systemd，三个进程直接在 Trae 终端里跑：

| 进程 | 启动方式 | 说明 |
|---|---|---|
| Flask 主应用 | `python app.py` | 遗留入口，后续挂 /api/v1 Blueprint |
| RQ worker | `rq worker dd pr` | dd=背调慢队列，pr=舆情快队列 |
| 前端 dev server | `npm run dev`（web/ 目录） | Vite，代理 API 到 Flask |

systemd 服务化推迟到 P1（多人使用后），避免过早固化进程参数。

端口规划：Flask 8080（沿用）、Vite dev 5173、PG 5432（仅本机）、Redis 6379（仅本机）。PG/Redis 只监听 localhost，不做对外暴露。

---

## 5. P0 进度与后续步骤

**已完成（已入库或待本次提交）**：
- ✅ 全部设计文档（本目录 5 份）
- ✅ `bettafish-main/backend/migrations/001_core_schema.sql`（core.* 9 张表，环境无关）

**服务器就位后（顺序执行）**：
1. 执行 §2 安装 + §3 初始化验证（预计半天内）
2. RQ worker 骨架（dd/pr 双队列 + 心跳写 `core.task.heartbeat_at`）
3. ReportEngine 去单例改造（`flask_interface.py:31-32` 全局单例 → Redis task_store）
4. InsightEngine 执行体抽离 Streamlit（runner + on_progress 回调）
5. SSE 结构化进度 + `/api/v1/tasks` /objects /artifacts
6. React 前端（案卷列表/详情/证据抽屉）
7. 投资尽调模板（12 章）+ 证据后校验

**P0 验收标准（不变，见设计文档 §6.1）**：业务方拿到一份报告，随机挑 5 个结论，每一个都能在 30 秒内点开看到原文出处。

---

## 6. 风险与注意事项

| # | 事项 | 说明 |
|---|---|---|
| 1 | 服务器 Ubuntu 版本未知 | 22.04 与 24.04 命令略有差异，§2 已双轨标注；拿到服务器先 `lsb_release -a` |
| 2 | 内网 GitHub 访问 | 公司服务器如访问不了 GitHub，改为工作站打包 rsync/scp 上传 |
| 3 | requirements 全量安装慢 | torch 等 ML 包体积大；P0 骨架阶段用精简依赖先行 |
| 4 | 服务器资源未知 | 设计文档假定的 64G 单机场景；若配置更低，P0 无影响（单任务跑通即可），P1 再评估 |
| 5 | `.env` 不入库 | 密钥（LLM API key 等）在服务器上手写，`.gitignore` 已排除 |
