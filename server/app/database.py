"""数据库会话与 ORM 基类（骨架阶段用 create_all 建表，表结构稳定后引入 Alembic）"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def reset_engine_for_tests():
    """测试切换数据库后重建引擎"""
    global _engine
    _engine = None


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401 确保模型已注册

    Base.metadata.create_all(get_engine())
