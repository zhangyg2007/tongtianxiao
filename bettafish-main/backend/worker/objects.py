"""core.object / core.artifact 的 PG 读写（/api/v1 支撑）。

复用 store.get_conn 的短连接模式；P0 只提供对象注册与产物查询，
实体对齐（kb.* 合并）与证据链写入在 P1+ 补。
"""

from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from .store import get_conn  # noqa: F401  (re-export for convenience)

OBJECT_TYPES = ("company", "person", "event")


def create_object(
    object_type: str,
    display_name: str,
    natural_key: str | None = None,
    display_meta: str | None = None,
    scope_dept_id: int | None = None,
) -> int:
    """注册一个对象，返回 object_id。

    幂等：同 (object_type, natural_key) 已存在时直接返回既有 id。
    """
    if object_type not in OBJECT_TYPES:
        raise ValueError(f"object_type 必须是 {OBJECT_TYPES} 之一")
    with get_conn() as conn, conn.cursor() as cur:
        if natural_key:
            cur.execute(
                "SELECT object_id FROM core.object "
                "WHERE object_type = %s AND natural_key = %s",
                (object_type, natural_key),
            )
            row = cur.fetchone()
            if row:
                return row[0]
        cur.execute(
            """
            INSERT INTO core.object
                (object_type, natural_key, display_name, display_meta, scope_dept_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING object_id
            """,
            (object_type, natural_key, display_name, display_meta, scope_dept_id),
        )
        return cur.fetchone()[0]


def get_object(object_id: int) -> dict | None:
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute("SELECT * FROM core.object WHERE object_id = %s", (object_id,))
        return cur.fetchone()


def list_objects(
    q: str | None = None,
    object_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """对象列表/搜索（q 模糊匹配 display_name）。"""
    where, params = [], []
    if q:
        where.append("display_name ILIKE %s")
        params.append(f"%{q}%")
    if object_type:
        where.append("object_type = %s")
        params.append(object_type)
    sql = "SELECT * FROM core.object"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT %s"
    params.append(max(1, min(limit, 200)))
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def list_artifacts(
    task_id: str | None = None,
    object_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """产物列表（按 task_id 或 object_id 过滤）。"""
    where, params = [], []
    if task_id:
        where.append("task_id = %s")
        params.append(task_id)
    if object_id is not None:
        where.append("object_id = %s")
        params.append(object_id)
    sql = "SELECT * FROM core.artifact"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(max(1, min(limit, 200)))
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def get_artifact(artifact_id: str) -> dict | None:
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            "SELECT * FROM core.artifact WHERE artifact_id = %s", (artifact_id,)
        )
        return cur.fetchone()
