"""管理员路由：系统配置代理（含脱敏与审计）、基座引擎状态代理"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..bettafish import BettaFishError, bettafish_request
from ..database import get_db
from ..models import ConfigAudit, User
from ..security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# 敏感配置键（GET 回显脱敏；PUT 时原样转发给基座）
_SENSITIVE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|API_?ID", re.IGNORECASE)
_MASK = "******"


class ConfigUpdate(BaseModel):
    configs: dict[str, str]


def _mask_configs(configs: dict) -> dict:
    return {k: (_MASK if _SENSITIVE.search(k) and v else v) for k, v in configs.items()}


@router.get("/configs")
def get_configs():
    try:
        resp = bettafish_request("GET", "/api/config")
    except BettaFishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {**resp, "config": _mask_configs(resp.get("config", {}))}


@router.put("/configs")
def update_configs(
    req: ConfigUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    try:
        resp = bettafish_request("POST", "/api/config", json_body={"config": req.configs})
    except BettaFishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not resp.get("success"):
        raise HTTPException(status_code=400, detail=resp.get("message", "配置更新被基座拒绝"))
    for key, new_value in req.configs.items():
        db.add(ConfigAudit(user_id=user.id, config_key=key, old_value_masked=None))
    db.commit()
    return {"success": True, "updated": list(req.configs)}


@router.get("/system/status")
def system_status():
    try:
        return bettafish_request("GET", "/api/system/status")
    except BettaFishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/system/start")
def system_start():
    try:
        return bettafish_request("POST", "/api/system/start")
    except BettaFishError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
