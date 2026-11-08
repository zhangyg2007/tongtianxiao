"""core.evidence 的 PG 读写（/api/v1 与任务处理器共用）。

证据是一等公民（设计文档 §2.3）：
- fact  = 归一化事实断言（可检索、可聚合、进评分卡）
- quote = 原文片段（LLM 不可改写，争议时自证）
- content_hash 幂等：同一 (fact + source_url + quote) 重复写入不产生脏数据
"""

import hashlib
from datetime import datetime

import psycopg2
import psycopg2.extras

from .store import get_conn


def insert_evidence(
    object_id: int,
    fact: str,
    fact_type: str,
    source_type: str,
    source_url: str,
    quote: str | None = None,
    source_name: str | None = None,
    task_id: str | None = None,
    value_json: dict | None = None,
    published_at: datetime | None = None,
    confidence: int = 85,
    confidence_reason: str | None = None,
) -> int:
    """插入 core.evidence，返回 evidence_id（content_hash 幂等）。"""
    content_hash = hashlib.sha256(
        f"{fact}|{source_url}|{quote or ''}".encode("utf-8")
    ).hexdigest()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.evidence
                (object_id, task_id, fact, fact_type, value_json, source_type,
                 source_name, source_url, quote, published_at, confidence,
                 confidence_reason, content_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash, source_url)
                DO UPDATE SET fact = EXCLUDED.fact
            RETURNING evidence_id
            """,
            (
                object_id,
                task_id,
                fact,
                fact_type,
                psycopg2.extras.Json(value_json) if value_json else None,
                source_type,
                source_name,
                source_url,
                quote,
                published_at,
                confidence,
                confidence_reason,
                content_hash,
            ),
        )
        return cur.fetchone()[0]


def get_evidence(evidence_id: int) -> dict | None:
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            "SELECT * FROM core.evidence WHERE evidence_id = %s", (evidence_id,)
        )
        return cur.fetchone()


def list_evidence(
    object_id: int | None = None,
    task_id: str | None = None,
    fact_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """证据列表（按 object_id / task_id / fact_type 过滤）。"""
    where, params = [], []
    if object_id is not None:
        where.append("object_id = %s")
        params.append(object_id)
    if task_id:
        where.append("task_id = %s")
        params.append(task_id)
    if fact_type:
        where.append("fact_type = %s")
        params.append(fact_type)
    sql = "SELECT * FROM core.evidence"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY published_at DESC NULLS LAST, evidence_id DESC LIMIT %s"
    params.append(max(1, min(limit, 500)))
    with get_conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(sql, params)
        return cur.fetchall()
