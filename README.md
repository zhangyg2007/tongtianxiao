# 通天晓（TongTianXiao）— 基于微舆 BettaFish 的舆情分析定制项目

本项目基于开源多智能体舆情分析系统 [BettaFish（微舆）](https://github.com/666ghj/BettaFish) v3.0.0 进行定制，目标是构建一个**本地舆情数据储备与知识库平台**：持续采集沉淀舆情语料、为自有模型生产微调（SFT）数据集、预留 RAG 集成能力，并通过 Web 应用与微信小程序提供基础配置和舆情分析功能。

> 本项目仅用于**学习与实验**，不做商业用途、不分发。遵循上游 GPL-2.0 协议，版权归原作者所有。

## 已完成的定制工作

### 1. 基座升级：v1.0.0 → v3.0.0

将上游代码从 v1.0.0 全量升级至 v3.0.0（`bettafish-main/`，git tag v3.0.0 引入），获得的关键能力：

- **配置体系**：`.env` + pydantic 校验，支持 `/api/config` 在线读写（基础配置页的现成后端）
- **数据库**：MySQL / PostgreSQL 双支持（`DB_DIALECT`，默认 PostgreSQL），全链路含 MindSpider 爬虫
- **报告引擎 V2**：七阶段流水线 + Document IR，交互式 HTML / 矢量 PDF / Markdown 导出，内存峰值 < 1GB
- **GraphRAG**：内置知识图谱构建与查询（`/api/graph/*` + 图谱查看器），可直接对接 RAG 软件
- **实时反馈**：报告生成 SSE 进度流（`/api/report/stream/<task_id>`），小程序可用轮询对接
- **搜索源**：新增 Anspire（默认，成本约为博查一半）；小红书爬虫签名修复
- 6 套报告模板（企业品牌/市场竞争/日常监测/政策行业/社会热点/突发事件危机公关）

### 2. 定制设计文档（v2）

`bettafish-main/design_document.md` — 基于用户需求重写的完整设计：

- 零侵入旁路架构（不修改基座源码，FastAPI 业务层挂载）
- PostgreSQL 15 + pgvector 统一数据底座（舆情库 / 业务库 / 向量库）
- 微调数据生产管线（采集 → 清洗 → 情感标注 → SFT JSONL 导出 → 版本管理）
- Ubuntu 24.04 本地服务器部署方案与 M1-M5 里程碑计划
- GPL-2.0 合规说明（学习实验、不分发、不商用）

### 3. M1 部署物（`bettafish-main/deploy/`）

| 文件 | 说明 |
|------|------|
| `M1_DEPLOY.md` | Ubuntu 24.04 完整部署步骤 + 故障排查 |
| `docker-compose.m1.yml` | 基座 + pgvector/pgvector:pg15 编排（含健康检查） |
| `prepare_env.sh` | 一键生成 `.env` 并补齐数据库指向 |
| `init_db.sql` | 首次建库自动启用 pgvector |
| `verify_m1.sh` | 一键验收：健康检查 → 配置 → 数据库 → 引擎启动 → 完整分析 → PDF 导出，PASS/FAIL 汇总 |

### 4. 前端骨架

- `web/`：Vue 3 + Vite + TypeScript + Pinia，已建登录/注册/首页/分析页骨架
- `wxapp/`：微信小程序原生框架骨架（登录/分析/报告/个人中心规划见设计文档）

## 目录结构

```
.
├── bettafish-main/          # BettaFish v3.0.0 基座（原版源码 + 定制文件）
│   ├── design_document.md   # 定制设计文档 v2
│   └── deploy/              # M1 部署物（compose / 环境准备 / 验收脚本）
├── web/                     # Web 前端（Vue3 + Vite + TS）
└── wxapp/                   # 微信小程序
```

## 快速开始（M1：基座部署）

在 Ubuntu 24.04 服务器上：

```bash
# 1. 安装 Docker（见 bettafish-main/deploy/M1_DEPLOY.md）
# 2. 准备环境配置
bash bettafish-main/deploy/prepare_env.sh && vim bettafish-main/.env   # 填写 LLM 与搜索 API Key
# 3. 启动
docker compose -f bettafish-main/deploy/docker-compose.m1.yml up -d
# 4. 初始化爬虫数据库（可选，M3 前必须）
docker compose -f bettafish-main/deploy/docker-compose.m1.yml exec bettafish python MindSpider/schema/init_database.py
# 5. 一键验收
bash bettafish-main/deploy/verify_m1.sh
```

## 未来规划

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1 | 基座部署（Ubuntu + compose + .env），跑通完整分析并导出 PDF | ✅ 部署物就绪，待服务器验收 |
| M2 | FastAPI 业务层（用户/JWT/任务索引/配置审计）+ Web 前端完整版 | ⏳ 计划中 |
| M3 | 微调数据管线：MindSpider 定时采集 → 清洗 → 情感标注 → SFT 数据集导出与版本管理 | ⏳ 计划中 |
| M4 | 微信小程序：微信登录、分析进度轮询、订阅消息通知 | ⏳ 计划中 |
| M5 | RAG 集成：pgvector 语料向量入库 + GraphRAG 图谱检索对接外部 RAG 软件 | ⏳ 计划中 |
| 远期 | MiroFish 预测引擎接入、独立向量库（Milvus/Qdrant）演进、采集平台扩展 | 💡 评估中 |

## 致谢

- [666ghj/BettaFish（微舆）](https://github.com/666ghj/BettaFish) — 多智能体舆情分析系统，本项目基座
