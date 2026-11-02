# 微舆舆情分析系统定制设计文档（v2 — 基于 BettaFish v3.0.0）

> 本版说明：设计基座由 v1.0.0 升级为 **BettaFish v3.0.0**（2025-12-23 发布），定位调整为**本地舆情数据储备与知识库建设、为自有模型生产微调数据**的学习实验平台（非商用、不分发），部署目标为 **Ubuntu 24.04 本地服务器**，并预留与 **RAG 相关软件**的集成接口。

## 1. 项目概述

### 1.1 项目背景

"微舆"（BettaFish）是一个从 0 实现的多智能体舆情分析系统，用户像聊天一样提出分析需求，多智能体自动完成全网社媒数据采集、多维分析与报告生成。

本项目在 v3.0.0 基座之上做定制，核心目的是：

1. **舆情数据储备**：通过 MindSpider 爬虫体系持续采集、沉淀本地舆情语料库（PostgreSQL）
2. **微调数据生产**：对语料进行清洗、情感标注、结构化导出（JSONL/CSV），为自有模型的微调（SFT）提供高质量数据集
3. **知识库与 RAG 集成**：语料向量化入库（pgvector），对接后续 RAG 软件；复用基座内置 GraphRAG 知识图谱能力
4. **基础配置与舆情分析**：通过 Web 应用与微信小程序提供可视化配置和舆情分析能力（学习实验用途）

### 1.2 定制原则

- **零侵入复用基座**：不修改 BettaFish 源码，业务能力以旁路服务（FastAPI 业务层）挂载，便于跟随上游更新
- **能用不造**：基座已提供配置管理、报告生成、日志流、GraphRAG 等 API，直接复用
- **学习实验定位**：内网部署、简化安全设计、不做商业级高可用

### 1.3 基座版本与关键变化（v1.0.0 → v3.0.0）

| 能力 | v1.0.0（旧） | v3.0.0（现基座） |
|------|-------------|------------------|
| 配置体系 | 手改 `config.py` 重启生效 | `.env` + pydantic 校验，Web UI 在线读写（`/api/config`） |
| 数据库 | 仅 MySQL | **MySQL / PostgreSQL 双支持**（`DB_DIALECT`，默认 PostgreSQL），compose 自带 postgres:15 |
| 报告引擎 | 单轮 HTML 生成 | Report Engine V2：七阶段流水线 + Document IR，HTML/矢量 PDF/Markdown 导出 |
| 实时反馈 | 仅 Socket.IO | Socket.IO + **SSE**（`/api/report/stream/<task_id>`）+ 日志 API |
| GraphRAG | 无 | 内置知识图谱构建与查询（`GRAPHRAG_ENABLED` 开关、`/api/graph/*`、图谱查看器） |
| 内存占用 | 较高 | 峰值 < 1GB |
| 报告模板 | 3 套 | 6 套（企业品牌/市场竞争/日常监测/政策行业/社会热点/突发事件危机公关） |
| 爬虫 | MindSpider（MySQL） | MindSpider 全链路支持 PostgreSQL，小红书签名修复 |
| 搜索源 | Tavily/博查 | + Anspire（默认，成本约博查一半） |
| 预测 | 无 | 预测引擎 MiroFish 为独立仓库（可选二期接入） |

## 2. 定制需求范围

| 编号 | 需求 | 承载端 | 实现方式 |
|------|------|--------|----------|
| R1 | 基础配置（LLM/搜索/数据库/GraphRAG 开关） | Web | 复用基座 `/api/config` + 配置页；业务层做鉴权代理 |
| R2 | 舆情分析（提问 → 多智能体 → 报告） | Web / 小程序 | 复用 `/api/search`、`/api/report/*` 全套 API |
| R3 | 舆情数据储备 | 服务端 | MindSpider 定时采集（APScheduler 调度容器） |
| R4 | 微调数据生产 | 服务端 + Web 管理页 | 自研数据管线模块（清洗/标注/导出/版本管理） |
| R5 | RAG 集成 | 服务端 | pgvector 同库方案 + GraphRAG 复用 |
| R6 | 用户体系与微信小程序 | 小程序 + FastAPI | 自研（JWT、微信授权登录、订阅消息） |

## 3. 基座能力盘点（复用 vs 自研）

### 3.1 直接复用的基座 API（端口 5000）

| API | 方法 | 说明 |
|-----|------|------|
| `/api/search` | POST | 舆情分析总入口，payload `{"query": "..."}`，分发至 Insight/Media/Query 三个引擎（内部 8601-8603） |
| `/api/report/generate` | POST | 触发 Report Engine V2 生成报告 |
| `/api/report/stream/<task_id>` | GET(SSE) | 报告生成实时进度流（小程序亦可用） |
| `/api/report/result/<task_id>` | GET | 报告结果（支持 `/json` 结构化） |
| `/api/report/download/<task_id>` | GET | 下载 HTML 报告 |
| `/api/report/export/pdf/<task_id>` | GET | 导出矢量 PDF（Pango 自检） |
| `/api/report/export/md/<task_id>` | GET | 导出 Markdown |
| `/api/report/templates` | GET | 6 套报告模板列表 |
| `/api/report/log`、`/api/report/log/clear` | GET/POST | 报告引擎日志 |
| `/api/config` | GET/POST | 在线读写 `.env` 配置（LLM、DB、GraphRAG 开关等） |
| `/api/system/status`、`/api/system/start`、`/api/system/shutdown` | GET/POST | 引擎（Streamlit 8501-8503）生命周期管理 |
| `/api/forum/log`、`/api/forum/log/history` | GET/POST | Agent 论坛协作记录（可用于展示智能体辩论过程） |
| `/api/graph/latest`、`/api/graph/<report_id>`、`/api/graph/query`、`/graph-viewer/<id>` | GET/POST | GraphRAG 知识图谱查询与可视化 |
| `/api/status` | GET | 健康检查 |

### 3.2 需自研的部分

- 用户体系（注册/登录/JWT/RBAC、微信 openid 绑定）
- 分析任务索引层（将基座的"无任务态"分析包装为可查询、可追溯的任务记录）
- 微信小程序网关（登录、订阅消息、轮询式进度）
- **微调数据管线**（清洗、标注、导出、数据集版本管理）
- 调度器（MindSpider 定时采集）

## 4. 总体架构

```
┌────────────────┐   ┌────────────────┐
│  微信小程序      │   │  Web (Vue3+Vite)│
└───────┬────────┘   └───────┬────────┘
        │  HTTPS/轮询         │  HTTP/SSE
        └─────────┬───────────┘
                  ▼
        ┌──────────────────┐
        │  Nginx (内网网关)  │  ← 静态资源(web dist) + 反向代理
        └───┬──────────┬───┘
            ▼          ▼
┌────────────────┐  ┌──────────────────────┐
│ BettaFish 基座  │  │ 业务层 FastAPI (:8000) │ ← 自研，零侵入
│ Flask (:5000)   │  │ · 用户/JWT/微信登录     │
│ · 多智能体引擎   │  │ · 任务索引/数据集管理    │
│ · Report V2    │  │ · 小程序网关/订阅消息    │
│ · GraphRAG     │  └──────────┬─────────────┘
│ · Streamlit×3  │             │
└───────┬────────┘             │
        │                      │
        ▼                      ▼
┌─────────────────────────────────────────────┐
│            数据与中间件层                      │
│  PostgreSQL 15 (+pgvector)  Redis  (可选)    │
│  · 舆情语料库(MindSpider写入)                  │
│  · 业务库(users/tasks/reports/datasets)      │
│  · 向量库(舆情embedding, RAG共用)             │
└─────────────────────────────────────────────┘
        ▲
┌───────┴────────┐
│ 调度器 APScheduler│ → MindSpider 定时采集 → 舆情库
└────────────────┘
        ▲
┌───────┴─────────────────────────────┐
│ 微调数据管线：清洗→情感标注→导出JSONL    │ → 数据集目录(版本化)
└─────────────────────────────────────┘
```

## 5. 技术栈

### 5.1 基座（不改动）
- Python 3.11、Flask 2.3.3 + flask-socketio、Streamlit 1.28.1
- SQLAlchemy 2.0.35（DB_DIALECT=postgresql，asyncpg 驱动）
- Report Engine V2（IR → HTML/PDF/MD 渲染器，离线字体与 Chart.js）

### 5.2 业务扩展层（自研）
- FastAPI + Uvicorn：REST API、SSE 代理、微信回调
- APScheduler：MindSpider 定时采集与数据管线定时任务（替代原设计的 Celery+Redis，内网单机足够，降低复杂度）
- SQLAlchemy 2.x：业务库 ORM
- PyJWT、httpx

### 5.3 前端
- Web：Vue 3 + Vite + TypeScript + Pinia + Element Plus（沿用现有 `web/` 骨架），实时进度用 **SSE**（EventSource）
- 小程序：原生框架（沿用现有 `wxapp/` 骨架），进度用 **定时轮询**（Socket.IO 原生小程序不兼容，v1 设计中的 WebSocket 方案作废），完成通知用微信订阅消息

### 5.4 数据
- **PostgreSQL 15 + pgvector 扩展**（舆情库、业务库、向量库同实例分库/分 schema）
- Redis：可选，用于会话缓存与限流

## 6. Web 应用设计

### 6.1 功能模块

| 模块 | 主要功能 | 说明 |
|------|---------|------|
| 用户管理 | 注册、登录、信息管理 | 业务层实现 |
| 舆情分析 | 提问、进度流、结果查看 | 代理基座 `/api/search` + `/api/report/stream` |
| 报告管理 | 历史、在线预览、PDF/MD 下载 | 业务层建索引，下载代理基座导出接口 |
| **数据集管理**（新增） | 语料统计、导出任务、数据集版本列表与下载 | 业务层实现，对应 R3/R4 |
| 系统配置 | LLM/搜索/DB/GraphRAG 可视化配置 | 页面调业务层代理 → 基座 `/api/config`；配置变更需管理员权限并留审计 |
| 监控中心 | 引擎状态、日志 | 代理基座 `/api/system/status`、`/api/forum/log` |

### 6.2 页面清单（对齐现有 web/ 骨架）

- 登录/注册（LoginView/RegisterView，已有骨架）
- 首页（HomeView）：快速分析入口、热门话题、最近报告
- 舆情分析（AnalysisView）：提问表单 + SSE 进度 + 论坛协作过程展示 + 报告预览
- 报告管理：列表/筛选/预览/导出
- 数据集管理（新增）：采集量看板、导出任务创建（时间范围/平台/情感/条数）、版本列表、JSONL 下载
- 系统配置（管理员）：分组表单渲染基座配置项（参考基座 `templates/index.html` 的配置 schema）
- 监控中心（管理员）

## 7. 微信小程序设计

| 页面 | 功能 | 实时方案 |
|------|------|---------|
| 登录页 | 微信一键登录（code → 业务层换 JWT） | - |
| 首页 | 快速分析、最近报告 | - |
| 分析页 | 提交分析、查看进度 | 轮询业务层任务进度（10s 间隔） |
| 报告列表/详情 | 历史、预览摘要、分享 | - |
| 个人中心 | 信息、设置 | 订阅消息授权 |

- 完成通知：业务层在报告生成后调用微信订阅消息接口推送
- 报告下载：小程序内提供 PDF 下载链接（内网 Wi-Fi 下可访问）

## 8. 数据模型（PostgreSQL）

### 8.1 业务库（business）

```sql
-- 用户表
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  email VARCHAR(100) UNIQUE,
  wechat_openid VARCHAR(100) UNIQUE,
  role VARCHAR(10) NOT NULL DEFAULT 'user',      -- user / admin
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 分析任务索引表（包装基座无任务态的分析请求）
CREATE TABLE analysis_tasks (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  query TEXT NOT NULL,
  report_task_id VARCHAR(64),                    -- 基座 Report Engine 的 task_id
  status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending/running/completed/failed
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 报告索引表（正文由基座落盘 final_reports/，此处存元数据）
CREATE TABLE reports (
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT REFERENCES analysis_tasks(id),
  title VARCHAR(255) NOT NULL,
  file_path VARCHAR(500),
  pdf_path VARCHAR(500),
  md_path VARCHAR(500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 系统配置审计表（敏感项仍以 .env 为唯一事实源）
CREATE TABLE config_audits (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  config_key VARCHAR(100) NOT NULL,
  old_value_masked VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 8.2 数据集库（dataset）

```sql
-- 微调数据集版本
CREATE TABLE fine_tune_datasets (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,                    -- 如 weibo_sft_v1
  format VARCHAR(20) NOT NULL DEFAULT 'jsonl',   -- jsonl / csv
  schema_type VARCHAR(30) NOT NULL,              -- sft_messages / sft_instruction
  record_count INTEGER NOT NULL DEFAULT 0,
  source_filter JSONB NOT NULL DEFAULT '{}',     -- 时间范围/平台/情感/最小长度
  labeling_model VARCHAR(100),                   -- 标注所用情感模型
  file_path VARCHAR(500) NOT NULL,
  created_by BIGINT REFERENCES business.users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 8.3 舆情语料库（由 MindSpider 建表，定制侧只读 + 附加标注列）

```sql
-- 以 MindSpider schema 为准；定制侧通过视图附加情感标注结果
CREATE TABLE sentiment_labels (
  source_table VARCHAR(50) NOT NULL,             -- 来源表，如 xhs_note_comment
  source_id BIGINT NOT NULL,
  label VARCHAR(20) NOT NULL,                    -- positive/neutral/negative
  confidence REAL NOT NULL,
  model VARCHAR(100) NOT NULL,                   -- 标注模型标识
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (source_table, source_id, model)
);

-- 向量表（RAG 共用）
CREATE TABLE corpus_embeddings (
  id BIGSERIAL PRIMARY KEY,
  source_table VARCHAR(50) NOT NULL,
  source_id BIGINT NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1024),                        -- pgvector，维度按所选 embedding 模型
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 9. API 设计

### 9.1 业务层 API（FastAPI :8000，前缀 `/api`）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/auth/register`、`/auth/login` | POST | 用户注册/登录（JWT） |
| `/auth/wx/login` | POST | 小程序 code 换 openid + JWT |
| `/user/profile` | GET/PUT | 用户信息 |
| `/tasks` | POST | 创建分析任务（内部调基座 `/api/search` + `/api/report/generate`，落 analysis_tasks） |
| `/tasks`、`/tasks/:id` | GET | 任务列表/详情（进度由业务层轮询基座 `/api/report/progress` 汇聚） |
| `/reports`、`/reports/:id` | GET | 报告索引 |
| `/reports/:id/download?format=pdf\|md\|html` | GET | 代理基座导出接口 |
| `/datasets` | POST/GET | 创建导出任务 / 数据集版本列表 |
| `/datasets/:id/download` | GET | 下载 JSONL/CSV |
| `/admin/configs` | GET/PUT | 管理员读写配置（代理基座 `/api/config` + 审计） |
| `/admin/system` | GET/POST | 引擎状态与启停（代理基座 `/api/system/*`） |
| `/wx/notify/subscribe` | POST | 订阅消息登记 |

### 9.2 基座 API（:5000）

直接复用 3.1 节所列接口，前端不直连（统一走 Nginx `/bettafish/` 前缀由业务层鉴权代理，防止绕过用户体系）。

## 10. 微调数据生产管线（新增核心模块）

### 10.1 流程

```
MindSpider 定时采集 ──► 舆情语料库(PostgreSQL)
        │
        ▼
[清洗] 去重(内容hash) / 去广告水军(规则+LLM可选) / 长度过滤 / 敏感信息脱敏
        │
        ▼
[标注] SentimentAnalysisModel 打标(多语言模型为主, BERT/Qwen 备选, 双模型一致才采信)
        │          └► 结果写 sentiment_labels
        ▼
[导出] 按筛选条件组装样本 → JSONL(SFT格式) → 数据集目录(按版本存放)
        │
        ▼
[管理] fine_tune_datasets 登记 → Web 数据集管理页 / 下载
```

### 10.2 SFT 数据格式（jsonl，每行一条）

```json
{"messages": [
  {"role": "system", "content": "你是一个社交媒体舆情分析助手。"},
  {"role": "user", "content": "分析以下微博评论的情感倾向，输出 positive/neutral/negative 与理由。\n评论：这个产品真的很不错"},
  {"role": "assistant", "content": "{\"label\": \"positive\", \"confidence\": 0.92, \"reason\": \"...\"}"}
]}
```

- 标注模型输出作为 `assistant` 目标；可选附带原文平台/时间元信息到 `user` 段
- 每个数据集版本记录 `source_filter` 与 `labeling_model`，保证可复现

### 10.3 调度

- APScheduler 容器每日定时触发 MindSpider（话题提取 + 深度爬取），平台/关键词清单由 Web 配置页维护（写 MindSpider 关键词表）
- 导出任务由 Web 手动触发（管理员），异步执行并轮询状态

## 11. RAG 集成方案

### 11.1 方案 A：pgvector 同库（推荐起步）

- 在同一 PostgreSQL 实例启用 pgvector 扩展，舆情文本 embedding 后写入 `corpus_embeddings`
- 后续 RAG 软件以**只读账号**直连该库检索，或经业务层提供检索 API
- embedding 模型维度写入表结构注释，更换模型需重建向量表

### 11.2 方案 B：独立向量库（数据量大后演进）

- 同步服务将清洗后语料推送至 Milvus/Qdrant；业务层保留统一写入接口，RAG 软件无感切换

### 11.3 GraphRAG 复用

- 基座开启 `GRAPHRAG_ENABLED=True` 后，报告生成时自动构建知识图谱
- RAG/前端可直接调用 `/api/graph/query` 做图谱检索，`/graph-viewer/<id>` 提供可视化页面
- 也可将图谱导出（nodes/edges JSON）投喂给外部 RAG 软件作为知识源

## 12. 部署方案（Ubuntu 24.04 本地服务器）

### 12.1 Docker Compose 拓扑

```yaml
services:
  nginx:        # 80 端口，静态 web dist + /api → fastapi + /bettafish → 5000
  bettafish:    # ghcr.io/666ghj/bettafish:latest，5000 + 8501-8503
  db:           # postgres:15（+pgvector 扩展），5444→5432
  fastapi:      # 业务层 :8000（自建镜像，业务代码 + 数据管线）
  scheduler:    # APScheduler（可与 fastapi 合并进程，规模小则不拆）
```

### 12.2 关键步骤

1. Ubuntu 24.04 安装 Docker Engine + Compose 插件
2. `cp .env.example .env`，填写 7 组 LLM 配置（Insight/Media/Query/Report/MindSpider/ForumHost/KeywordOptimizer）、搜索 API（默认 Anspire）、`DB_DIALECT=postgresql`
3. `docker compose up -d`；进入 db 容器创建业务库与 pgvector 扩展
4. MindSpider 初始化：`python MindSpider/schema/init_database.py`（首次）
5. 业务库执行迁移脚本（8.1/8.2 建表）
6. `cd web && npm run build`，dist 交给 nginx 托管
7. 健康检查：`GET /api/status`（基座）、`GET /api/health`（业务层）

### 12.3 资源与运维

- 基座内存峰值 < 1GB；全栈建议 8GB 内存 / 100GB 数据盘起步
- 数据目录挂载：`db_data`（库）、`final_reports`（报告）、`datasets`（数据集）、`logs`
- 备份：每日 `pg_dump` 舆情库与业务库 + 数据集目录 rsync
- 内网环境：Nginx 无需 HTTPS（如需远程访问可加自签证书或 Tailscale）
- Windows 开发机仅跑 web/wxapp 前端开发；基座与数据管线全部跑在 Ubuntu 服务器

## 13. 安全性设计（内网实验版，精简）

- JWT 认证 + 简单 RBAC（user/admin）
- 密码 bcrypt；配置页敏感值（API Key）回显脱敏
- 基座端口不对外，仅经业务层代理访问
- 爬虫合规：遵守目标平台 robots 与频率限制，仅学习研究用途

## 14. 测试计划

- 业务层：pytest 覆盖认证、任务索引、数据集导出（含 SFT 格式校验）
- 基座联调：以固定 query 验证 `/api/search` → 报告 → PDF 导出全链路
- 管线：抽样人工核对标注准确率（每版本 ≥200 条）
- 前端：web 浏览器手动回归 + 小程序真机预览

## 15. 里程碑

| 阶段 | 内容 | 验收标准 |
|------|------|---------|
| M1 | 基座部署（Ubuntu + compose + .env） | `/api/status` 通，跑通一次完整分析并导出 PDF |
| M2 | 业务层 + Web（登录/分析/报告/配置） | Web 全流程可用，配置页可改 LLM 并生效 |
| M3 | 数据管线 + 定时采集 | 自动采集 3 天，导出首个 ≥1 万条 SFT 数据集 |
| M4 | 小程序 | 真机完成登录→分析→收订阅消息闭环 |
| M5 | RAG 集成（pgvector + GraphRAG 开关） | RAG 软件可检索语料向量与图谱 |

## 16. 合规与风险

- **License**：BettaFish 为 GPL-2.0。本项目仅内部学习实验使用，不分发、不商用；web/ 与 wxapp/ 为原创代码，通过 API 调用基座服务，不构成 GPL 传染。若未来变更商用或分发计划，需重新评估并联系作者授权
- **爬虫风险**：平台风控可能导致采集中断，关键词与频率需克制；不用于商业决策
- **上游跟进**：基座以 git clone（tag v3.0.0）引入于 `bettafish-main/`，旧 v1.0.0 备份于 `bettafish-v1.0.0.bak/`（确认无需后可删除）；升级时 `git fetch --tags && git checkout <新tag>` 后回归 M1 验收项
- **MiroFish 预测**（v3.0.0 配套独立仓库）：暂不纳入，二期按需评估接入

## 17. 总结

本设计基于 BettaFish v3.0.0 的"零侵入旁路"策略：基座负责舆情分析、报告、配置、GraphRAG 等重能力，自研业务层补齐用户体系、任务索引、微信小程序网关与微调数据管线；数据底座统一到 PostgreSQL（+pgvector），同时服务舆情储备、微调数据生产与 RAG 集成三条线。整体复杂度可控，符合本地服务器学习实验定位，并为后续接入预测引擎与独立向量库预留演进空间。
