"""业务层配置（pydantic-settings，环境变量前缀 BTX_）"""
import warnings
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BTX_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 业务库；生产: postgresql+psycopg2://bettafish:bettafish@db:5432/business
    database_url: str = "sqlite:///./btx_dev.db"
    # 通过 BTX_JWT_SECRET 注入；缺失时保留占位值，启动时告警（不随机生成，保证可复现）
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    bettafish_base_url: str = "http://localhost:8080"
    # 任务管线轮询参数（秒）：引擎产出等待上限 / 报告生成等待上限 / 轮询间隔
    engine_wait_max: int = 7200
    report_wait_max: int = 7200
    poll_interval: int = 60


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        warnings.warn(
            "BTX_JWT_SECRET 未设置，正在使用占位值；生产环境必须通过环境变量注入。",
            RuntimeWarning,
            stacklevel=2,
        )
    return settings
