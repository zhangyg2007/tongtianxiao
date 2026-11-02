#!/usr/bin/env bash
# M1 环境准备：复制 .env.example → .env 并补齐数据库指向（与 docker-compose.m1.yml 一致）
# 用法: bash deploy/prepare_env.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo "[SKIP] .env 已存在，不覆盖。如需重建请先备份删除。"
else
  cp .env.example .env
  echo "[OK] 已从 .env.example 生成 .env"
fi

# 数据库指向 compose 内的 db 服务（幂等替换）
sed -i 's|^DB_HOST=.*|DB_HOST=db|' .env
sed -i 's|^DB_USER=.*|DB_USER=bettafish|' .env
sed -i 's|^DB_PASSWORD=.*|DB_PASSWORD=bettafish|' .env
sed -i 's|^DB_NAME=.*|DB_NAME=bettafish|' .env
sed -i 's|^DB_DIALECT=.*|DB_DIALECT=postgresql|' .env
echo "[OK] 已写入数据库配置: DB_HOST=db, DB_USER=bettafish, DB_NAME=bettafish, DB_DIALECT=postgresql"

echo
echo "=========================================="
echo " 还需手工填写以下配置（vim .env）："
echo "  - 7 组 LLM: INSIGHT_/MEDIA_/QUERY_/REPORT_/MINDSPIDER_/FORUM_HOST_/KEYWORD_OPTIMIZER_"
echo "  - 搜索源:   ANSPIRE_API_KEY（默认）或 TAVILY_API_KEY"
echo "  填写完成后执行:"
echo "    docker compose -f deploy/docker-compose.m1.yml up -d"
echo "    bash deploy/verify_m1.sh"
echo "=========================================="
