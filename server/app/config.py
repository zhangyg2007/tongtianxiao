"""业务层配置（pydantic-settings，环境变量前缀 BTX_）"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BTX_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 业务库；生产: postgresql+psycopg2://bettafish:bettafish@db:5432/business
    database_url: str = "sqlite:///./btx_dev.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    bettafish_base_url: str = "http://localhost:5000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
