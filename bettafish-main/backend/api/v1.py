"""/api/v1 统一接口（P0：任务 / 对象 / 产物 + SSE 结构化进度）。

设计（前端与产品形态升级设计 §4）：
- 任务提交走 backend.worker.enqueue.submit_task → RQ → 处理器注册表，
  状态/进度落 core.task + core.task_step（PG），与 UI 会话彻底解耦；
- SSE 轮询 core.task / core.task_step 的变更并推结构化事件
  （task / step / end），断线重连后全量补发快照，天然无遗漏；
- P0 无鉴权（内部工具），requested_by 由调用方透传，默认 0。

路由总览：
    POST /tasks                      提交任务
    GET  /tasks                      任务列表
    GET  /tasks/<task_id>            任务详情（含 steps）
    POST /tasks/<task_id>/cancel     取消任务
    GET  /tasks/<task_id>/events     SSE 进度流
    GET  /objects                    对象列表/搜索
    POST /objects                    注册对象
    GET  /objects/<object_id>        对象详情（含最近任务）
    GET  /artifacts                  产物列表
    GET  /artifacts/<artifact_id>    产物详情
"""

import json
import time
import uuid
from datetime import date, datetime

from flask import Blueprint, Response, jsonify, request, stream_with_context
from loguru import logger

from backend.worker import enqueue, objects, store

api_v1_bp = Blueprint("api_v1", __name__)

TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
SSE_POLL_INTERVAL = 1.0  # 秒
SSE_HEARTBEAT_INTERVAL = 15  # 秒


# ====== 工具 ======

def _serialize(value):
    """PG 行 → JSON 安全类型（UUID/datetime/RealDictRow 递归转换）。"""
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _ok(data, status=200):
    return jsonify(_serialize(data)), status


def _err(message, status=400):
    return jsonify({"error": message}), status


def _payload() -> dict:
    return request.get_json(silent=True) or {}


# ====== 任务 ======

@api_v1_bp.post("/tasks")
def create_task():
    data = _payload()
    product_line = (data.get("product_line") or "").strip()
    task_type = (data.get("task_type") or "").strip()
    if product_line not in ("dd", "pr"):
        return _err("product_line 必须是 dd（背调）或 pr（舆情）")
    if not task_type:
        return _err("task_type 不能为空")
    input_dict = data.get("input") or {}
    if not isinstance(input_dict, dict):
        return _err("input 必须是对象")
    try:
        task_id = enqueue.submit_task(
            product_line=product_line,
            task_type=task_type,
            requested_by=int(data.get("requested_by") or 0),
            input=input_dict,
            object_id=data.get("object_id"),
            project_id=data.get("project_id"),
            idempotency_key=data.get("idempotency_key"),
        )
    except Exception as e:  # 含幂等冲突等 DB 约束
        logger.exception("提交任务失败")
        return _err(f"提交任务失败: {e}", 500)
    return _ok({"task_id": task_id, "status": "queued"}, 201)


@api_v1_bp.get("/tasks")
def list_tasks():
    rows = store.list_tasks(
        product_line=request.args.get("product_line") or None,
        status=request.args.get("status") or None,
        object_id=(
            int(request.args["object_id"])
            if request.args.get("object_id", "").isdigit()
            else None
        ),
        limit=int(request.args.get("limit", 50)),
        offset=int(request.args.get("offset", 0)),
    )
    return _ok({"tasks": rows, "count": len(rows)})


@api_v1_bp.get("/tasks/<task_id>")
def get_task(task_id: str):
    task = store.get_task(task_id)
    if task is None:
        return _err("任务不存在", 404)
    return _ok({"task": task, "steps": store.get_steps(task_id)})


@api_v1_bp.post("/tasks/<task_id>/cancel")
def cancel_task(task_id: str):
    if store.get_task(task_id) is None:
        return _err("任务不存在", 404)
    ok = enqueue.cancel_task(task_id)
    return _ok({"task_id": task_id, "canceled": bool(ok)})


# ====== 任务 SSE 进度流 ======

def _sse(event_type: str, data) -> str:
    return f"event: {event_type}\ndata: {json.dumps(_serialize(data), ensure_ascii=False)}\n\n"


def _task_events(task_id: str):
    """轮询 core.task / core.task_step，变更即推事件；终态发 end 后关闭。"""
    last_task_sig = None
    last_step_sig: dict[int, tuple] = {}
    last_heartbeat = time.monotonic()
    # 首条立即推全量快照（断线重连天然补齐）
    while True:
        task = store.get_task(task_id)
        if task is None:
            yield _sse("error", {"message": "任务不存在"})
            return
        sig = (task["status"], task["progress"], task["stage"], str(task["error"]))
        if sig != last_task_sig:
            yield _sse("task", task)
            last_task_sig = sig
        for step in store.get_steps(task_id):
            step_sig = (step["status"], step["finished_at"])
            if last_step_sig.get(step["seq"]) != step_sig:
                yield _sse("step", step)
                last_step_sig[step["seq"]] = step_sig
        if task["status"] in TERMINAL_STATUSES:
            yield _sse("end", {"task_id": task_id, "status": task["status"]})
            return
        now = time.monotonic()
        if now - last_heartbeat >= SSE_HEARTBEAT_INTERVAL:
            yield ": heartbeat\n\n"
            last_heartbeat = now
        time.sleep(SSE_POLL_INTERVAL)


@api_v1_bp.get("/tasks/<task_id>/events")
def task_events(task_id: str):
    if store.get_task(task_id) is None:
        return _err("任务不存在", 404)
    return Response(
        stream_with_context(_task_events(task_id)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 反代时不缓冲
        },
    )


# ====== 对象 ======

@api_v1_bp.get("/objects")
def list_objects():
    rows = objects.list_objects(
        q=request.args.get("q") or None,
        object_type=request.args.get("object_type") or None,
        limit=int(request.args.get("limit", 50)),
    )
    return _ok({"objects": rows, "count": len(rows)})


@api_v1_bp.post("/objects")
def create_object():
    data = _payload()
    object_type = (data.get("object_type") or "").strip()
    display_name = (data.get("display_name") or "").strip()
    if not display_name:
        return _err("display_name 不能为空")
    try:
        object_id = objects.create_object(
            object_type=object_type,
            display_name=display_name,
            natural_key=data.get("natural_key"),
            display_meta=data.get("display_meta"),
            scope_dept_id=data.get("scope_dept_id"),
        )
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        logger.exception("注册对象失败")
        return _err(f"注册对象失败: {e}", 500)
    return _ok({"object_id": object_id}, 201)


@api_v1_bp.get("/objects/<int:object_id>")
def get_object(object_id: int):
    obj = objects.get_object(object_id)
    if obj is None:
        return _err("对象不存在", 404)
    recent_tasks = store.list_tasks(object_id=object_id, limit=20)
    artifacts = objects.list_artifacts(object_id=object_id, limit=20)
    return _ok({"object": obj, "tasks": recent_tasks, "artifacts": artifacts})


# ====== 产物 ======

@api_v1_bp.get("/artifacts")
def list_artifacts():
    rows = objects.list_artifacts(
        task_id=request.args.get("task_id") or None,
        object_id=(
            int(request.args["object_id"])
            if request.args.get("object_id", "").isdigit()
            else None
        ),
        limit=int(request.args.get("limit", 50)),
    )
    return _ok({"artifacts": rows, "count": len(rows)})


@api_v1_bp.get("/artifacts/<artifact_id>")
def get_artifact(artifact_id: str):
    row = objects.get_artifact(artifact_id)
    if row is None:
        return _err("产物不存在", 404)
    return _ok({"artifact": row})
