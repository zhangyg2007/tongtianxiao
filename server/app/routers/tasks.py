"""分析任务索引：创建任务并调基座 /api/search，状态落库"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bettafish import BettaFishError, bettafish_request
from ..database import get_db
from ..models import AnalysisTask, User
from ..security import get_current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    query: str = Field(min_length=2, max_length=2000)


class TaskOut(BaseModel):
    id: int
    query: str
    status: str
    report_task_id: str | None
    error: str | None

    model_config = {"from_attributes": True}


def _dispatch_search(task_id: int, query: str) -> None:
    """后台分发至基座（引擎拉起与爬取分析耗时较长，不阻塞请求）"""
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, task_id)
        try:
            resp = bettafish_request("POST", "/api/search", json_body={"query": query})
            task.status = "running" if resp.get("success") else "failed"
            task.error = None if resp.get("success") else str(resp)[:500]
        except BettaFishError as exc:
            task.status = "failed"
            task.error = str(exc)[:500]
        db.commit()
    finally:
        db.close()


@router.post("", status_code=201)
def create_task(
    req: TaskCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = AnalysisTask(user_id=user.id, query=req.query, status="pending")
    db.add(task)
    db.commit()
    background.add_task(_dispatch_search, task.id, req.query)
    return TaskOut.model_validate(task)


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tasks = db.scalars(
        select(AnalysisTask).where(AnalysisTask.user_id == user.id).order_by(AnalysisTask.id.desc())
    ).all()
    return [TaskOut.model_validate(t) for t in tasks]


@router.get("/{task_id}")
def get_task(
    task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    task = db.get(AnalysisTask, task_id)
    if task is None or (task.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="任务不存在")
    out = TaskOut.model_validate(task).model_dump()
    # 已产生基座报告任务时附带实时进度
    if task.report_task_id:
        try:
            out["report_progress"] = bettafish_request(
                "GET", f"/api/report/progress/{task.report_task_id}"
            )
        except BettaFishError:
            out["report_progress"] = None
    return out
