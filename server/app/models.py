"""ORM 模型：业务库四表（对应设计文档 8.1 节）"""
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# SQLite（开发/测试）仅对 INTEGER 主键自增，PostgreSQL 用 BIGINT
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(100), unique=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(100), unique=True)
    role: Mapped[str] = mapped_column(String(10), default="user")  # user / admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AnalysisTask(Base):
    """分析任务索引：包装基座"无任务态"的分析请求"""

    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    query: Mapped[str] = mapped_column(Text)
    # 基座 Report Engine 的 task_id（报告生成后回填）
    report_task_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Report(Base):
    """报告索引：正文由基座落盘 final_reports/，此处存元数据"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255))
    report_task_id: Mapped[str] = mapped_column(String(64), index=True)  # 基座报告 task_id
    file_path: Mapped[str | None] = mapped_column(String(500))
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    md_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ConfigAudit(Base):
    """系统配置变更审计（敏感项事实源仍是基座 .env）"""

    __tablename__ = "config_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    config_key: Mapped[str] = mapped_column(String(100))
    old_value_masked: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# M3 预留：数据集表在 server/app/models_dataset.py 中实现，避免骨架阶段混入未用模型
