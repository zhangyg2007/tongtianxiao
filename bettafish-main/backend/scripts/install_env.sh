#!/usr/bin/env bash
# ============================================================
# install_env.sh — Ubuntu 24.04 x64 环境一键安装
# 用法：在服务器上 git pull 仓库后执行
#   bash bettafish-main/backend/scripts/install_env.sh
# 依赖：sudo 权限；预计 10-20 分钟（含 NodeSource/deadsnakes 源添加）
# 幂等：可重复执行
# ============================================================
set -euo pipefail

echo "==> [1/4] 基础工具 + PostgreSQL 16 + Redis 7（apt 公共环境，systemd 托管）"
sudo apt update
sudo apt install -y git build-essential postgresql redis-server
# weasyprint（报告 PDF 导出）运行所需系统库
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0

echo "==> [2/4] Python 3.11（24.04 自带 3.12，遗留钉死包需要 3.11，走 deadsnakes）"
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.11 python3.11-venv python3.11-dev

echo "==> [3/4] Node.js 20 LTS（前端构建用，NodeSource）"
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

echo "==> [4/4] 服务自检"
sudo systemctl enable --now postgresql redis-server
pg_isready && echo "PostgreSQL: OK"
redis-cli ping && echo "Redis: OK"
python3.11 --version
node --version

echo "==> 完成。下一步：bash bettafish-main/backend/scripts/init_db.sh"
