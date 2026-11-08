#!/usr/bin/env bash
# ============================================================
# setup_venv.sh — P0 开发虚拟环境（精简依赖，先跑通链路）
# 用法：init_db.sh 之后执行
#   bash bettafish-main/backend/scripts/setup_venv.sh
# 说明：全量 requirements.txt 含 torch（200MB+），P0 骨架阶段
#       先装精简集；后续跑遗留引擎时再装全量。
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV="$REPO_ROOT/.venv"

echo "==> 创建 venv（Python 3.11）：$VENV"
python3.11 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> 安装 P0 精简依赖"
pip install --upgrade pip
pip install flask "redis>=4.6" rq psycopg2-binary asyncpg loguru "pydantic>=2" \
    python-dotenv tenacity apscheduler \
    openai json-repair pydantic-settings matplotlib scipy wordcloud weasyprint

echo "==> 完成。激活方式：source $VENV/bin/activate"
