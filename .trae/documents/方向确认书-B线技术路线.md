# 方向确认书：B 线技术路线（公司背调 + 舆情监控）

> 日期：2026-11-09
> 状态：**生效**（本文件为 B 线执行的唯一方向依据；与 `ARCHITECTURE.md` 冲突时以代码事实为准）
> 归档分支：`archive/m2-20261104`（已推送，冻结于 `3e035f7`）
> 主线：`main` @ `7e0c36e`

---

## 一屏结论

| 项 | 结论 |
|---|---|
| **技术主线（一句话）** | **Flask 单进程承载 Web + `/api/v1`，Redis + RQ 跑异步任务，PostgreSQL `core` schema 做唯一事实源，React + Vite 做工作台；Streamlit 仅作调试入口，不做产品化。** |
| **A 线（M2）** | 只归档、不删除、不再投入。`server/`、`web/`、`wxapp/` 标记 legacy，从 README 主入口摘除；物理删除暂缓。 |
| **分支现状** | ✅ `main 7e0c36e`（= origin/main）；✅ `archive/m2-20261104 3e035f7`（已推 origin）；✅ 本地 `feat/b-line-cleanup 7e0c36e`（未推送、未切换、无提交）。 |
| **数据库** | 本地 PostgreSQL 持久化，`core` 9 表够跑背调 MVP；舆情监控需补 4 张表；MySQL 仅作舆情采集原始库并存；pgvector 保留安装但不使用。 |
| **接下来的三件事** | ① 15 个悬空文件拆 4 个提交（0.5 人日）<br>② 配置与依赖收口：`config.example.py` + `rq` 进 requirements（0.3 人日）<br>③ M2 目录标 legacy + 建 `ARCHITECTURE.md`（0.5 人日） |
| **30 天目标** | 第 2 周末产出**最小可用背调报告**（输入公司名 → 9 个事实章节有数据 → 证据可点开）；第 4 周末舆情最小闭环。总投入 **18–22 人日**（⚠️估算）。 |

---

## 二、Git 执行结果

### 2.1 执行前核实 ✅

| 检查 | 结果 |
|---|---|
| 当前分支 | `main` |
| HEAD | `7e0c36ef33ecc4914df36fa5361831110184aec8` |
| `git remote -v` | `origin https://github.com/zhangyg2007/tongtianxiao.git`（fetch/push 一致） |
| 远端 main | `7e0c36ef33ecc4914df36fa5361831110184aec8`（与本地一致） |
| M2 最后提交 | `3e035f729c5fc1de1fea2def9ee33b7dc0c80dcb`，2026-11-04T16:26:59+08:00，`feat(M2): 任务管线闭环——报告任务回填与索引落库` ✅ 与预期一致 |
| 未提交清单 | 5 个已修改 + 10 个未跟踪条目 = 15 个文件（详见 2.4） |

### 2.2 执行的命令与返回 ✅

```powershell
# 1) 创建归档分支（不切换工作区）
git branch archive/m2-20261104 3e035f729c5fc1de1fea2def9ee33b7dc0c80dcb
# 返回：无输出，成功

# 2) 推送归档分支
git push origin archive/m2-20261104
# 返回：
#  * [new branch]      archive/m2-20261104 -> archive/m2-20261104
#  （PowerShell 把 git 的 stderr 进度输出渲染成了 RemoteException，但 exit code = 0，且明确出现 [new branch]）

# 3) 创建后续工作分支（不切换、不提交）
git branch feat/b-line-cleanup 7e0c36ef33ecc4914df36fa5361831110184aec8

# 4) 复核
git branch -vv
git ls-remote --heads origin
```

最终状态：

```text
  archive/m2-20261104 3e035f7 feat(M2): 任务管线闭环——报告任务回填与索引落库
  feat/b-line-cleanup 7e0c36e feat(P0): 投资尽调 12 章模板 + 评分卡三态 + 证据后校验（investment_dd）
* main                7e0c36e [origin/main] feat(P0): 投资尽调 12 章模板 + 评分卡三态 + 证据后校验（investment_dd）

远端：
3e035f729c5fc1de1fea2def9ee33b7dc0c80dcb  refs/heads/archive/m2-20261104
7e0c36ef33ecc4914df36fa5361831110184aec8  refs/heads/main
```

### 2.3 未执行的操作（按约束）

- ❌ 未 commit、未 reset、未 rebase、未 force-push、未删除分支、未 `git clean`
- ❌ 未修改 15 个未提交文件的任何内容
- ❌ 未在 `archive/m2-20261104` 上新建提交（因此**没有**写 `ARCHIVE.md`，归档说明仅记录在本文件 §3.2）
- ❌ `feat/b-line-cleanup` 仅存在于本地，未推送（用户未授权推送该分支）
- ⚠️ 云服务器 `/opt/gitdownload/tongtianxiao` 仍未连接，服务器侧 remote 与 HEAD 未核实

### 2.4 15 个未提交文件清单 ✅

| 类型 | 文件 |
|---|---|
| 已修改（5） | `bettafish-main/app.py`、`bettafish-main/backend/dd/pipeline.py`、`bettafish-main/backend/dd/report.py`、`bettafish-main/backend/dd/template.py`、`bettafish-main/backend/worker/jobs.py` |
| 新增代码（4 路径） | `bettafish-main/backend/dd/writer.py`、`bettafish-main/backend/sources/`（`base.py`/`juchao.py`/`akshare_src.py`/`tianyancha.py`/`case_file.py`）、`bettafish-main/backend/worker/entities.py`、`bettafish-main/tests/test_sources.py` |
| 新增文档（6 路径） | `.trae/documents/Git历史审计.md`、`.trae/documents/设计冲突复盘.md`、`.trae/documents/多Agent协作Prompt工程方案.md`、`.trae/documents/改造模块清单.md`、`.trae/documents/cases/`、`.trae/documents/prompts/` |

---

## 三、技术路线（确定，不提供并列选项）

### 3.1 技术主线

| 层 | 确定选型 | 为什么是它 | 重新评估的触发条件 |
|---|---|---|---|
| **后端 Web** | **Flask**（现有 `app.py` + `ReportEngine/flask_interface.py` + `backend/api/v1.py` Blueprint） | 基座已经是 Flask，进程管理、Streamlit 编排、旧接口都在这里；P0 已把 `/api/v1` 以 Blueprint 方式挂上，继续走 Flask 的边际成本最低 | 单实例持续 QPS > 50，或必须使用 WebSocket 长连接、或后台 IO 并发 > 200 协程时，评估迁移 FastAPI（届时只迁 `/api/v1`，不动 `app.py`） |
| **任务队列** | **Redis + RQ**（`dd` / `pr` 双队列） | 已有可运行骨架；Python 原生、无额外 broker；与现有 worker/scheduler 代码一致；运维只需 Redis 一个组件 | 日任务量 > 10,000，或需要复杂 DAG、跨队列依赖、精细重试策略时，评估 Celery / Temporal |
| **数据库（业务）** | **本地 PostgreSQL 15+，`core` schema** | 关系模型 + JSONB 足够表达证据/产物；事务保证"证据—引用—报告"一致性；本地部署无网络依赖 | 证据表 > 5,000 万行，或需要全文+向量混合检索时，评估引入专用检索引擎（OpenSearch / 向量库） |
| **前端** | **React 18 + TypeScript + Vite**（`frontend/`） | 工作台已实现案卷/任务/证据三视图；静态构建后可由 Flask 直接托管，生产不需要 Node 常驻 | 需要 SSR/SEO（本项目不需要）或移动端原生体验时，才评估 Next.js / 小程序 |
| **缓存** | **Redis**（任务事件流；不作为唯一事实源） | 与 RQ 共用实例，零额外运维 | 无 |
| **采集** | MindSpider（舆情）+ `backend/sources/`（背调：巨潮/AkShare/天眼查/案件） | 背调用结构化 API 更稳，舆情用现有爬虫生态 | 数据源封禁率 > 30% 或需要亿级历史回溯时，评估商业数据源 |

**一句话**：B 线继续在"基座内改造"，不新增独立后端进程。

### 3.2 A 线（M2）处置

| 对象 | 处置 | 理由 | 触发物理删除的条件 |
|---|---|---|---|
| `server/`（FastAPI 四表 + 轮询管线） | **标 legacy，不删除、不运行** | 它的前提是"基座单任务、黑盒"，已被 RQ 打破；但用户模型/鉴权设计有参考价值 | `core.app_user` 落地且鉴权迁移完成，且连续 2 个版本无人引用 → 移入 `legacy/` 或删除 |
| `web/`（Vue3 管理端） | **标 legacy，不维护** | 缺 3 个页面、API 端口指向 5000 而后端在 8000，修复成本 ≥ 重写 | React 工作台覆盖用户/权限管理后删除 |
| `wxapp/`（微信小程序） | **标 legacy，不维护** | 仅 1/7 页，P1 已砍移动端 | 直接归档到 `legacy/`，本阶段即可 |
| 代码本身 | **不删除** | 归档分支 `archive/m2-20261104` 已保留完整历史 | — |

**本阶段动作**：
1. 在根 `README.md` 顶部写明"现行入口 = Flask 5000 + React 5173；`server/`、`web/`、`wxapp/` 为 M2 遗留，不参与构建"；
2. 三个目录各放一个 `LEGACY.md`（3 行说明 + 归档分支名 + 冻结点 sha）；
3. 暂不物理删除，避免误伤历史引用。

### 3.3 数据库方案（本地 PostgreSQL 持久化）

#### 3.3.1 `core` 9 张表是否够用

**背调 MVP：够用 ✅**

| 现有表 | 覆盖 |
|---|---|
| `core.object` / `object_alias` | 公司主体、别名、USCC 去重 |
| `core.task` / `task_step` | 任务、步骤、心跳、幂等 |
| `core.evidence` | 事实 + 原文 + 来源 + 置信度 |
| `core.artifact` / `artifact_block` / `artifact_citation` / `artifact_anchor` | 报告、章节块、句级引证、PDF 锚点 |

**缺口（按优先级）**

| 缺什么 | 影响 | 何时补 |
|---|---|---|
| `core.app_user` | `core.task.requested_by BIGINT NOT NULL` 目前无对应用户表，P0 只能写常量 `1` | 第 4 周（与权限一起），或先建一张只有 id/name 的最小表 |
| `core.monitor_subject` / `monitor_rule` | 舆情监控的"监控谁、按什么词、多久跑一次"无处存 | 第 3 周（舆情闭环必备） |
| `core.article` / `core.mention` | 舆情原文与提及关系；现在只能塞进 `evidence`，无法做热度/时间序列 | 第 3 周 |
| `core.metric_daily` | 每日声量/情感/负面率趋势 | 第 4 周 |
| `core.source_config` | 数据源密钥/限流配置（当前在 `config.py`） | 随 P1 |

> 结论：**不为背调加表；为舆情加 4 张表（`monitor_subject`、`monitor_rule`、`article`、`metric_daily`），`mention` 可先并入 `article.object_id`。**

#### 3.3.2 pgvector：保留安装，不使用

- 现状 ✅：`bettafish-main/deploy/init_db.sql:5` 有 `CREATE EXTENSION IF NOT EXISTS vector;`，并预留 `corpus_embeddings`；`core` schema 完全不含向量列，代码全仓无读写。
- **决定：保留扩展安装（5–10 MB，无运行成本），但不建业务向量表、不做向量检索。**
- 动作：把 `init_db.sql` 中的 vector 段标注为"可选，失败可跳过"；本地初始化脚本加 `|| true` 容错。RAG/向量检索整体推迟到本阶段之后。

#### 3.3.3 MySQL 采集库与分析库的关系

**并存，不迁移，划清边界。**

| 库 | 角色 | 规则 |
|---|---|---|
| PostgreSQL `core` | 业务/证据/产物的**唯一事实源** | 所有读接口、报告生成只读这里 |
| MySQL（MindSpider） | 舆情**采集原始库**（笔记/评论/账号） | 仅采集进程写入；通过 `backend/sources/` 归一化后写入 `core.evidence`/`article` |

三条硬规则：
1. 禁止跨库 JOIN；
2. 禁止业务代码直连 MySQL（只允许采集适配层）；
3. `core` 中的证据必须保留 `source_url` + `content_hash`，可回溯到 MySQL 原始行，但不在查询时回表。

迁移到 PG 的触发条件：MySQL 单表 > 5,000 万行，或需要与证据做联合检索时，再评估。

#### 3.3.4 备份策略（本地服务器最小可行）

| 对象 | 方式 | 频率 | 保留 | 恢复演练 |
|---|---|---|---|---|
| PostgreSQL | `pg_dump -Fc core` → `backups/pg/core_YYYYMMDD.dump` | 每日 02:30 | 14 天 | 每月一次恢复到临时库 |
| 产物文件 | `tar czf artifacts_YYYYMMDD.tar.gz final_reports/ data/` | 每日 02:40 | 30 天 | 每季度 |
| Redis | 不备份（非事实源）；`appendonly yes` 仅防进程重启丢事件 | 实时 | — | — |
| 配置 | `.env` 手工保管，不入库 | 变更时 | — | — |

落地：新增 `bettafish-main/backend/scripts/backup.sh` + `crontab` 两行；单机场景不做异地，但每周手动拷一份到另一块盘（`⚠️` 若后续有合规要求再升级）。

### 3.4 B 线运行时形态

| 进程 | 是否常驻 | 端口 | 职责 | 内存估算 ⚠️ |
|---|---|---|---|---|
| PostgreSQL | 是 | 5432 | 唯一事实源 | 100–300 MB |
| Redis | 是 | 6379 | RQ 队列 + 事件流 | 10–50 MB |
| Flask（`python app.py`） | 是 | 5000 | Web + `/api/v1` + 旧 `/api/report` | 150–250 MB |
| RQ worker（`backend.worker.worker`） | 是 | 无 | 执行 dd/pr 任务 | 200–400 MB（跑 Insight 时 +800 MB–1.5 GB） |
| RQ scheduler（`backend.worker.scheduler`） | 是 | 无 | 每 60s 扫僵死任务 | 50–80 MB |
| React | **否**（生产用构建产物由 Flask 托管） | 5173（仅开发） | 工作台 | 开发时 200–400 MB |
| Streamlit ×3 | **否**（仅调试） | 8501/8502/8503 | 引擎原始视图 | 每个 150–250 MB |
| MySQL | 视舆情需求 | 3306 | 采集原始库 | 200–400 MB |

**最小常驻集合（背调）**：PG + Redis + Flask + worker + scheduler ≈ **0.6–1.1 GB**（不含模型加载峰值）。

**启动顺序**（必须）：
1. PostgreSQL → 2. Redis → 3. 执行 `core` 迁移 → 4. Flask → 5. RQ worker → 6. RQ scheduler → 7.（可选）Streamlit / React dev

**停止顺序**：worker → scheduler → Flask → Redis → PostgreSQL（避免任务执行中被杀）。

### 3.5 分支策略（最终版）

| 分支 | 用途 | 状态 |
|---|---|---|
| `main` | **唯一发布线，只走 B 线** | 受保护：禁止直推、禁止 force-push |
| `archive/m2-20261104` | M2 冻结归档（`3e035f7`） | 只读，不再提交 |
| `feat/<域>-<主题>` | 新功能 | 例：`feat/dd-sources`、`feat/pr-monitor`、`feat/ui-workbench` |
| `fix/<主题>` | 缺陷修复 | 例：`fix/veto-keywords` |
| `chore/<主题>` | 构建/依赖/配置 | 例：`chore/config-example` |
| `docs/<主题>` | 文档 | 例：`docs/architecture` |
| `feat/b-line-cleanup` | 本次 15 文件收口专用 | 已建，未推送、无提交 |

规则：
1. 改动 **> 3 个文件**、跨模块、涉及 schema/接口、涉及删除目录 → **必须开分支**；
2. 单文件小修可直接在 `main` 提交，但必须过 §3.6 清单；
3. 合并方式：**squash**，保持 main 线性；
4. PR 要求：标题含模块前缀；描述必须写"动机 + 影响面 + 验证方式"；至少自查清单全过；
5. `main` 禁止：force-push、直接 push 未经本地验证的 schema 变更、提交密钥。

### 3.6 提交前清单（每个分支合并前必过）

```text
[ ] 干净克隆能 import：临时 clone → 按 README 装依赖 → 关键模块导入成功
[ ] 依赖已声明：新增 import 的包全部进 requirements.txt
[ ] 配置可复现：新增配置项同步更新 config.example.py 与 .env.example
[ ] 无密钥：diff 中无 sk-*/token/password 明文
[ ] 测试通过：python -m unittest discover -s bettafish-main/tests
[ ] 文档同步：ARCHITECTURE.md 中受影响的入口/表/端口已更新
[ ] 工作区干净：git status 无未说明的悬空改动
```

### 3.7 接下来 30 天执行序列

| 周 | 任务 | 人日 ⚠️ | 产出物 |
|---|---|---|---|
| **W1（11/10–11/16）** | ① 15 文件拆 4 提交：`chore(config)` / `feat(sources)` / `feat(dd-writer)` / `docs(audit)` | 0.5 | 干净的 main + 可追溯提交 |
| | ② `config.example.py` + `.gitignore` 放行 + `rq` 进 requirements | 0.3 | 新克隆可启动 |
| | ③ `server/`、`web/`、`wxapp/` 标 legacy，README 改为 B 线入口 | 0.3 | 入口唯一 |
| | ④ 新建 `ARCHITECTURE.md`；现有文档统一加 status/baseline | 0.5 | 唯一事实源 |
| | ⑤ `ci_smoke.sh` + pre-push hook | 0.5 | 门禁可用 |
| | ⑥ `backup.sh` + cron | 0.3 | 每日备份 |
| **W2（11/17–11/23）** | ⑦ 数据源收口：巨潮/AkShare/天眼查/案件 → `core.evidence` 完整落库（含去重 `content_hash`） | 3 | 背调数据链可用 |
| | ⑧ 实体对齐：USCC `natural_key` + 别名合并 + 同名消歧 | 2 | 不串档 |
| | ⑨ LLM 章节写作 + 12 章模板联调，证据角标后校验 | 2 | **最小可用背调报告（里程碑）** |
| | ⑩ 端到端回归：`cases/real_002372` 跑通 9 个事实章节 | 1 | 回归报告 |
| **W3（11/24–11/30）** | ⑪ 舆情表：`monitor_subject` / `monitor_rule` / `article` / `metric_daily` | 1 | 迁移 002 |
| | ⑫ 关键词监控任务（`pr` 队列）+ 采集适配 | 3 | 舆情采集闭环 |
| | ⑬ 情感/热度聚合 + 日报模板 | 2 | 舆情日报 |
| **W4（12/1–12/7）** | ⑭ React 构建由 Flask `static` 托管，`/` 切工作台，旧页移 `/legacy` | 2 | 单入口 |
| | ⑮ 任务详情 SSE 统一到 `core.task_step`，旧 `/api/report` 标 deprecated | 1 | 状态单源 |
| | ⑯ 运维脚本与交接文档（启动/停止/备份/排障） | 1 | 可交接 |

**合计：18–22 人日**（⚠️ 基于改动面估算；W2 的 ⑦⑧ 是最大不确定项，若数据源封禁或字段缺失，可能 +2 人日）。

**里程碑定义**：
- **M-A（W2 末）最小可用背调报告**：输入公司名 → 生成 12 章报告 → 至少 9 个事实章节有证据 → 每个角标可点开原文。
- **M-B（W4 末）单入口工作台**：`http://server:5000/` 直接进 React 工作台，能建任务、看进度、看证据。

### 3.8 明确不做（本阶段主动放弃）

| 放弃项 | 原因 |
|---|---|
| A 线全部功能（JWT、多租户、用户管理、Vue 管理端、微信小程序） | 归属已归档；当前无多用户诉求 |
| Streamlit 产品化（美化、嵌入主流程） | 仅保留调试，React 才是产品界面 |
| 向量检索 / RAG / GraphRAG | pgvector 保留但不使用，推迟到背调闭环稳定后 |
| 实时推送（WebSocket / FastAPI 迁移） | SSE 足够；避免引入第二个后端 |
| 报告在线协同编辑 | 单人作业场景不需要 |
| 定时舆情告警（短信/邮件/企微） | 先做日报，告警在 P1 评估 |
| 历史 Git 重写、上游冗余清理 | 588 文件规模可控，重写风险 > 收益 |
| 移动端 | P1 已砍，无明确需求 |

### 3.9 风险与回退

| 风险 | 概率 | 影响 | 回退 |
|---|---|---|---|
| 数据源（天眼查/巨潮）限流或字段变更 | 中 | W2 延期 | `backend/sources/` 已抽象 `base.py`，单源可降级为手工 `case_file` 导入 |
| 本地 PG 磁盘不足（报告 + 证据） | 低 | 任务失败 | `backup.sh` 同盘保留 14 天 + 产物 30 天；监控 `df -h` |
| RQ worker 内存峰值（Insight 模型） | 中 | OOM | worker 并发固定 1；必要时把 Insight 拆独立队列限流 |
| 旧 `/api/report` 与 `/api/v1` 状态不一致 | 中 | 前端显示错乱 | W4 统一到 `core.task_step`；过渡期以 PG 为准 |
| 误删 legacy 目录 | 低 | 丢参考代码 | 归档分支已保留完整历史 |

---

## 附录：核实状态

**✅ 已核实**
- `main`/`origin/main` = `7e0c36e`；M2 末提交 = `3e035f7`
- `archive/m2-20261104` 已推送到 GitHub（`refs/heads/archive/m2-20261104 = 3e035f7`）
- 15 个未提交文件清单
- `core` 9 表结构（`001_core_schema.sql`）
- `core.task.requested_by BIGINT NOT NULL` 无对应用户表
- pgvector 仅出现在 `deploy/init_db.sql:5`，`core` 无向量列，代码无读写
- MySQL 由 MindSpider 独立配置（`DB_DIALECT=mysql`）
- 现有端口：Flask 5000、Streamlit 8501–8503、Vite 5173

**⚠️ 推断 / 未核实**
- 服务器 `/opt/gitdownload/tongtianxiao` 状态（不可达，未连接）
- 各进程内存占用（估算值，需实测）
- 30 天 18–22 人日（基于改动面估算，未做实现验证）
- 数据源可用性与限流阈值（需 W2 实测）
- MySQL 表规模（未连库）
