"""用户注册 / 登录（JWT）/ 微信登录占位"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=72)
    email: str | None = None


class WxLoginRequest(BaseModel):
    code: str


def _token_response(user: User) -> dict:
    return {"access_token": create_access_token(user.id, user.role), "token_type": "bearer"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == req.username)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    if req.email and db.scalar(select(User).where(User.email == req.email)):
        raise HTTPException(status_code=409, detail="邮箱已被注册")
    # 首个注册用户自动成为 admin（内网实验环境简化引导）
    is_first = db.scalar(select(User.id).limit(1)) is None
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        email=req.email,
        role="admin" if is_first else "user",
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _token_response(user)


@router.post("/wx/login")
def wx_login(req: WxLoginRequest):
    """M4 阶段实现：code 换 openid + 绑定/创建用户"""
    raise HTTPException(status_code=501, detail="微信登录将在 M4 阶段实现")
