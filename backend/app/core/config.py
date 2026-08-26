from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAGOPS_", extra="ignore")

    app_name: str = "ragops-api"
    environment: str = "local"
    database_url: str = "sqlite:///./ragops.db"
    log_level: str = "INFO"
    auto_create_schema: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
