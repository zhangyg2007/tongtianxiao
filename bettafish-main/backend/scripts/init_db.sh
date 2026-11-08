#!/usr/bin/env bash
# ============================================================
# init_db.sh — 建库并执行 core schema 迁移
# 用法：install_env.sh 之后执行
#   bash bettafish-main/backend/scripts/init_db.sh
# 幂等：createuser/createdb 已存在则跳过；DDL 全部 IF NOT EXISTS
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION="$SCRIPT_DIR/../migrations/001_core_schema.sql"

echo "==> 创建数据库用户与库（当前用户 $USER）"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$USER'" | grep -q 1 \
  || sudo -u postgres createuser --createdb "$USER"
createdb bettafish 2>/dev/null || echo "库 bettafish 已存在，跳过"

echo "==> 执行 core schema 迁移：$MIGRATION"
psql -v ON_ERROR_STOP=1 -d bettafish -f "$MIGRATION"

echo "==> 验证（预期 9 张表）："
psql -d bettafish -c "\dt core.*"
