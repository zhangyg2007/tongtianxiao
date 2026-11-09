"""worker 配置：.env 优先，默认值对齐 install_env.sh / init_db.sh 的产物。

约定（见 .trae/documents/P0-Ubuntu服务器部署与实施规划.md）：
- Redis: apt 直装，localhost:6379，无密码
- PG:    apt 直装，库名 bettafish，unix socket + peer 认证（OS 用户即 PG 用户）
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 代码目录 = bettafish-main/bettafish-main（worker/ 的上两级）
CODE_DIR = Path(__file__).resolve().parents[2]
# .env 优先取代码目录，其次 git 仓库根
for _candidate in (CODE_DIR, CODE_DIR.parent):
    if (_candidate / ".env").is_file():
        load_dotenv(_candidate / ".env")
        break

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# 空 host 走 unix socket + peer 认证，与 init_db.sh 建的库对齐
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///bettafish")

# 双队列：dd=背调（慢任务），pr=舆情（快任务），避免互相阻塞
QUEUE_DD = "dd"
QUEUE_PR = "pr"
QUEUES = [QUEUE_DD, QUEUE_PR]

# 心跳：worker 每 15s 写 core.task.heartbeat_at；
# 扫描器每 60s 巡检，running 且心跳超 2min 判僵死
HEARTBEAT_INTERVAL_SECONDS = 15
ZOMBIE_THRESHOLD_SECONDS = 120
REAP_INTERVAL_SECONDS = 60

# 单任务硬超时（RQ job timeout），背调最长 2h
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "7200"))
