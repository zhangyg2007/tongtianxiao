"""Redis 任务存储：报告任务的跨进程状态与事件流。

背景（设计文档 §3.1）：原 flask_interface.py 用模块级全局变量
`current_task` + 内存队列管理任务，整个系统同一时刻只能跑一个报告，
且任务状态随 Flask 进程存活。本模块把状态迁到 Redis：

- bf:rtask:{task_id}         Hash    任务字段（status/progress/文件路径...）
- bf:rtask:{task_id}:events  Stream  事件流（SSE 用 XREAD BLOCK 消费）
- bf:rtask:index             List    最近任务 id（LRANGE 供 /status 展示）

TTL 7 天，防止遗留任务无限累积。事件 id 直接用 Redis Stream 的
条目 id（形如 "1728483945000-3"），断线重连时浏览器会把 Last-Event-ID
原样带回，服务端 XRANGE 该 id 之后即可补发。
"""

import json
import os
from typing import Dict, List, Optional, Tuple

import redis
from loguru import logger

TASK_TTL_SECONDS = 7 * 24 * 3600
INDEX_MAX_LEN = 100

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """惰性建立 Redis 连接（decode_responses，统一返回 str）。"""
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.Redis.from_url(url, decode_responses=True)
    return _redis_client


def _task_key(task_id: str) -> str:
    return f"bf:rtask:{task_id}"


def _events_key(task_id: str) -> str:
    return f"bf:rtask:{task_id}:events"


def _normalize_after_id(after_id: Optional[str]) -> str:
    """把外部传入的 Last-Event-ID 规整成合法的 Stream id。"""
    if not after_id:
        return "0"
    after_id = str(after_id)
    if after_id == "$":
        return "$"
    # 合法形如 "ms-seq"；否则退回从头读
    parts = after_id.split("-")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        return after_id
    return "0"


def create_task(task_id: str, fields: Dict[str, str]) -> None:
    """新建任务（Hash + 索引）。字段值统一转 str 存储面上保持简单。"""
    r = get_redis()
    pipe = r.pipeline()
    pipe.hset(_task_key(task_id), mapping={k: str(v) for k, v in fields.items()})
    pipe.expire(_task_key(task_id), TASK_TTL_SECONDS)
    pipe.lpush("bf:rtask:index", task_id)
    pipe.ltrim("bf:rtask:index", 0, INDEX_MAX_LEN - 1)
    pipe.execute()


def set_fields(task_id: str, mapping: Dict[str, str]) -> None:
    """更新部分字段并续期。"""
    r = get_redis()
    pipe = r.pipeline()
    pipe.hset(_task_key(task_id), mapping={k: str(v) for k, v in mapping.items()})
    pipe.expire(_task_key(task_id), TASK_TTL_SECONDS)
    pipe.execute()


def get_fields(task_id: str) -> Optional[Dict[str, str]]:
    """读取任务全部字段；不存在返回 None。"""
    data = get_redis().hgetall(_task_key(task_id))
    return data if data else None


def exists(task_id: str) -> bool:
    return bool(get_redis().exists(_task_key(task_id)))


def latest_task_ids(count: int = 1) -> List[str]:
    """最近的任务 id（新的在前），供 /status 展示。"""
    return get_redis().lrange("bf:rtask:index", 0, count - 1)


def publish_event(task_id: str, event_type: str, payload: Dict) -> str:
    """向事件流追加一条事件，返回 Stream 条目 id。"""
    r = get_redis()
    entry_id = r.xadd(
        _events_key(task_id),
        {
            "type": event_type,
            "task_id": task_id,
            "timestamp": _utc_now_iso(),
            "payload": json.dumps(payload, ensure_ascii=False),
        },
    )
    r.expire(_events_key(task_id), TASK_TTL_SECONDS)
    return str(entry_id)


def read_events(
    task_id: str,
    after_id: Optional[str] = None,
    block_ms: Optional[int] = None,
    count: int = 200,
) -> List[Dict]:
    """读取 after_id 之后的事件（含），转换为原事件结构。

    block_ms 提供时用 XREAD BLOCK 阻塞等待（SSE 长连接用），
    否则 XRANGE 一次性读取（断线重连补发用）。
    """
    after = _normalize_after_id(after_id)
    r = get_redis()
    if block_ms is not None:
        # XREAD 接受 "0" 起点（等价 0-0，从头返回），无新事件时阻塞
        result = r.xread({_events_key(task_id): after}, count=count, block=block_ms)
        if not result:
            return []
        entries = result[0][1]
    else:
        if after == "0":
            return _range_events(task_id, "-", "+", count)
        return _range_events(task_id, f"({after}", "+", count)

    events = []
    for entry_id, fields in entries:
        events.append(_entry_to_event(entry_id, fields))
    return events


def _range_events(task_id: str, start: str, end: str, count: int) -> List[Dict]:
    entries = get_redis().xrange(_events_key(task_id), min=start, max=end, count=count)
    return [_entry_to_event(entry_id, fields) for entry_id, fields in entries]


def _entry_to_event(entry_id, fields: Dict[str, str]) -> Dict:
    try:
        payload = json.loads(fields.get("payload", "{}"))
    except Exception:
        payload = {"message": fields.get("payload", "")}
    return {
        "id": str(entry_id),
        "type": fields.get("type", "message"),
        "task_id": fields.get("task_id", ""),
        "timestamp": fields.get("timestamp", ""),
        "payload": payload,
    }


def _utc_now_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"
