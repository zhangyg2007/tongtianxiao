# M1 部署指南 — BettaFish 基座（Ubuntu 24.04）

> 对应设计文档里程碑 M1：基座部署（Ubuntu + compose + .env）。
> 验收标准：`/api/status` 通；跑通一次完整分析并导出 PDF。

## 0. 前置条件

| 项 | 要求 |
|----|------|
| 服务器 | Ubuntu 24.04，建议 8GB+ 内存、100GB 数据盘 |
| 网络 | 可访问 GitHub（拉镜像）、各 LLM API、搜索 API |
| API 密钥 | 至少 7 组 LLM 配置 + 1 个搜索源（见第 3 步） |

## 1. 安装 Docker

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER   # 重新登录生效
```

## 2. 获取代码

```bash
git clone --depth 1 --branch v3.0.0 https://github.com/666ghj/BettaFish.git bettafish
cd bettafish
# ghcr.io 拉取慢时可换镜像源（deploy/docker-compose.m1.yml 中改 image 为
# ghcr.nju.edu.cn/666ghj/bettafish:latest）
```

## 3. 准备 .env

```bash
bash deploy/prepare_env.sh     # 复制 .env.example → .env，并自动补齐数据库指向
vim .env
```

必须在 `.env` 中填写的最小集合：

| 配置组 | 键 | 推荐模型/说明 |
|--------|-----|---------------|
| Insight Agent | `INSIGHT_ENGINE_API_KEY/_BASE_URL/_MODEL_NAME` | kimi-k2（platform.moonshot.cn） |
| Media Agent | `MEDIA_ENGINE_*` | gemini-2.5-pro（或中转） |
| Query Agent | `QUERY_ENGINE_*` | deepseek-chat |
| Report Agent | `REPORT_ENGINE_*` | gemini-2.5-pro（报告质量依赖强模型） |
| MindSpider Agent | `MINDSPIDER_*` | deepseek-chat |
| 论坛主持人 | `FORUM_HOST_*` | qwen-plus |
| SQL 关键词优化 | `KEYWORD_OPTIMIZER_*` | qwen-plus |
| 搜索源 | `TAVILY_API_KEY` 或 `ANSPIRE_API_KEY`（默认用 Anspire） | 二选一即可 |
| 数据库 | 已由脚本设为 `DB_HOST=db / DB_USER=bettafish / DB_PASSWORD=bettafish / DB_NAME=bettafish` | 与 compose 保持一致 |

注意：`DB_DIALECT=postgresql` 保持默认；`GRAPHRAG_ENABLED=false` M1 先关闭。

## 4. 启动服务

```bash
docker compose -f deploy/docker-compose.m1.yml up -d
docker compose -f deploy/docker-compose.m1.yml ps
```

- 数据库首次启动会自动执行 `deploy/init_db.sql`（启用 pgvector 扩展）
- BettaFish 容器健康检查通过（`start_period` 120s）后即可访问

## 5. 初始化 MindSpider 数据库 Schema（建议 M1 顺手完成，M3 前必须）

```bash
docker compose -f deploy/docker-compose.m1.yml exec bettafish \
  python MindSpider/schema/init_database.py
```

## 6. 一键验收

```bash
bash deploy/verify_m1.sh
```

脚本将自动完成并逐项打印 PASS/FAIL：

1. 基座 `/api/status` 健康检查
2. `/api/config` 配置加载检查
3. 数据库 `pg_isready` + pgvector 扩展检查
4. `POST /api/system/start` 启动三个 Streamlit 引擎（8501-8503）
5. `POST /api/search` 提交测试分析（默认“新能源汽车市场舆情分析”，可用环境变量 `QUERY` 覆盖）
6. 轮询 `/api/report/generate`（等待三引擎产出输入文件）→ 轮询 `/api/report/progress/<task_id>`
7. `GET /api/report/export/pdf/<task_id>` 下载 PDF 并校验文件大小

常用环境变量：

```bash
QUERY="某热点事件" SEARCH_WAIT_MAX=3600 bash deploy/verify_m1.sh
```

| 变量 | 默认 | 说明 |
|------|------|------|
| `BASE_URL` | http://localhost:5000 | 基座地址 |
| `QUERY` | 新能源汽车市场舆情分析 | 验收用分析主题 |
| `SEARCH_WAIT_MAX` | 2400 秒 | 等待三引擎产出结果的最长时间 |
| `REPORT_WAIT_MAX` | 5400 秒 | 等待报告生成的最长时间 |
| `PDF_OUT` | m1_final_report.pdf | PDF 输出路径 |

## 7. 常见问题

| 现象 | 处理 |
|------|------|
| 引擎启动失败 / 分析报 LLM 超时 | 检查 `.env` 对应 API Key 与 BASE_URL；先用 curl 直连 BASE_URL 验证连通性 |
| 报告生成一直报 `missing_files` | 三引擎未完成爬取分析：查看 `logs/` 与各 `*_streamlit_reports/`；延长 `SEARCH_WAIT_MAX` |
| 连不上数据库 | 确认 `DB_HOST=db`（compose 网络内主机名为 `db`，不是 localhost） |
| 镜像拉取超时 | 换 `ghcr.nju.edu.cn/666ghj/bettafish:latest` |
| Windows 编辑过脚本后报 `$'\r': command not found` | `sed -i 's/\r$//' deploy/*.sh` |
