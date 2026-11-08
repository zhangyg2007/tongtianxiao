"""core.task / core.task_step 的 PG 读写（psycopg2）。

设计要点：
- job_id == task_id（UUID 字符串），RQ job 与 core.task 一一对应；
- 每次操作短连接，P0 量级（每天几十任务 + 15s 一次心跳）完全够用，
  后续量大再换连接池；
- 所有状态迁移都是幂等 UPDATE，重试/重复调用不产生脏数据。
"""

import uuid
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from loguru import logger

from . import config


@contextmanager
def get_conn():
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_task(
    product_line: str,
    task_type: str,
    requested_by: int,
    input: dict | None = None,
    object_id: int | None = None,
    project_id: int | None = None,
    idempotency_key: str | None = None,
) -> str:
    """插入 core.task（status=queued），返回 task_id 字符串。"""
    task_id = str(uuid.uuid4())
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.task
                (task_id, product_line, task_type, object_id, input,
                 project_id, requested_by, idempotency_key, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'queued')
            """,
            (
                task_id,
                product_line,
                task_type,
                object_id,
                psycopg2.extras.Json(input or {}),
                project_id,
                requested_by,
                idempotency_key,
            ),
        )
    return task_id


def get_task(task_id: str) -> dict | None:
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute("SELECT * FROM core.task WHERE task_id = %s", (task_id,))
        return cur.fetchone()


def list_tasks(
    product_line: str | None = None,
    status: str | None = None,
    object_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """任务列表（新版分页，按创建时间倒序）。"""
    where, params = [], []
    if product_line:
        where.append("product_line = %s")
        params.append(product_line)
    if status:
        where.append("status = %s")
        params.append(status)
    if object_id is not None:
        where.append("object_id = %s")
        params.append(object_id)
    sql = "SELECT * FROM core.task"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params += [max(1, min(limit, 200)), max(0, offset)]
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_steps(task_id: str) -> list[dict]:
    """任务步骤列表（按 seq 升序）。"""
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            "SELECT * FROM core.task_step WHERE task_id = %s ORDER BY seq", (task_id,)
        )
        return cur.fetchall()


def mark_running(task_id: str, worker_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE core.task
            SET status = 'running', started_at = now(),
                heartbeat_at = now(), worker_id = %s
            WHERE task_id = %s AND status IN ('queued', 'running')
            """,
            (worker_id, task_id),
        )


def heartbeat(task_id: str) -> None:
    """心跳写心跳时间戳；任务不存在/已终态时静默无操作。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE core.task SET heartbeat_at = now() "
            "WHERE task_id = %s AND status = 'running'",
            (task_id,),
        )


def set_progress(task_id: str, progress: int, stage: str | None = None) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE core.task SET progress = %s, stage = COALESCE(%s, stage) "
            "WHERE task_id = %s",
            (max(0, min(100, progress)), stage, task_id),
        )


def mark_succeeded(task_id: str, result: dict | None = None) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE core.task SET status = 'succeeded', progress = 100, "
            "finished_at = now(), result = %s WHERE task_id = %s",
            (psycopg2.extras.Json(result or {}), task_id),
        )


def mark_failed(task_id: str, code: str, message: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE core.task SET status = 'failed', finished_at = now(), "
            "error = %s WHERE task_id = %s AND status <> 'succeeded'",
            (psycopg2.extras.Json({"code": code, "message": message}), task_id),
        )


def mark_canceled(task_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE core.task SET status = 'canceled', finished_at = now() "
            "WHERE task_id = %s AND status IN ('queued', 'running', 'waiting_input')",
            (task_id,),
        )


def append_step(task_id: str, seq: int, name: str, status: str = "running",
                detail: dict | None = None) -> None:
    """插入或推进一个 task_step（同一 (task_id, seq) 冲突时更新状态）。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.task_step (task_id, seq, name, status, started_at, detail)
            VALUES (%s, %s, %s, %s, now(), %s)
            ON CONFLICT (task_id, seq) DO UPDATE
                SET status = EXCLUDED.status, detail = EXCLUDED.detail
            """,
            (task_id, seq, name, status, psycopg2.extras.Json(detail or {})),
        )


def finish_step(task_id: str, seq: int, status: str = "succeeded",
                detail: dict | None = None) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE core.task_step
            SET status = %s, finished_at = now(),
                duration_ms = EXTRACT(EPOCH FROM (now() - started_at)) * 1000,
                detail = COALESCE(%s, detail)
            WHERE task_id = %s AND seq = %s
            """,
            (status, psycopg2.extras.Json(detail) if detail else None, task_id, seq),
        )


def reap_zombies(threshold_seconds: int = config.ZOMBIE_THRESHOLD_SECONDS) -> list[str]:
    """僵死任务收割：running 且心跳超时 → failed（heartbeat_lost）。

    返回被收割的 task_id 列表。注意：这里只改 core.task 状态；
    对应 RQ job 若真已死，其状态由 RQ 自身机制处理，两边互不依赖。
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE core.task
            SET status = 'failed', finished_at = now(),
                error = %s
            WHERE status = 'running'
              AND heartbeat_at < now() - make_interval(secs => %s)
            RETURNING task_id
            """,
            (
                psycopg2.extras.Json({
                    "code": "heartbeat_lost",
                    "message": f"心跳超过 {threshold_seconds}s 未更新，判定为僵死任务",
                }),
                threshold_seconds,
            ),
        )
        rows = [str(r[0]) for r in cur.fetchall()]
    if rows:
        logger.warning(f"僵死任务收割：{len(rows)} 个 -> {rows}")
    return rows
