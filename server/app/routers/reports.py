"""报告索引与下载代理（正文由基座落盘，此处只做鉴权与转发）"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bettafish import BettaFishError, stream_request
from ..database import get_db
from ..models import AnalysisTask, Report, User
from ..security import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

# 下载格式 → 基座接口路径
_DOWNLOAD_PATHS = {
    "html": "/api/report/download/{rtid}",
    "pdf": "/api/report/export/pdf/{rtid}",
    "md": "/api/report/export/md/{rtid}",
}
_MEDIA_TYPES = {"html": "text/html", "pdf": "application/pdf", "md": "text/markdown"}


@router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = (
        select(Report)
        .join(AnalysisTask, Report.task_id == AnalysisTask.id)
        .where(AnalysisTask.user_id == user.id)
        .order_by(Report.id.desc())
    )
    if user.role == "admin":
        stmt = select(Report).order_by(Report.id.desc())
    return [
        {
            "id": r.id,
            "task_id": r.task_id,
            "title": r.title,
            "report_task_id": r.report_task_id,
            "created_at": r.created_at,
        }
        for r in db.scalars(stmt)
    ]


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    format: str = "html",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if format not in _DOWNLOAD_PATHS:
        raise HTTPException(status_code=400, detail=f"format 仅支持 {list(_DOWNLOAD_PATHS)}")
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if user.role != "admin":
        task = db.get(AnalysisTask, report.task_id)
        if task is None or task.user_id != user.id:
            raise HTTPException(status_code=404, detail="报告不存在")
    try:
        resp, client = stream_request(
            "GET", _DOWNLOAD_PATHS[format].format(rtid=report.report_task_id)
        )
    except BettaFishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    filename = f"{report.report_task_id}.{format}"
    return StreamingResponse(
        resp.iter_bytes(),
        media_type=_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=BackgroundTask(client.close),
    )
