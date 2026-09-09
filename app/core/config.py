from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str
    environment: Literal["local", "staging", "prod"]
    database_url: str
    # None = 跟 environment 走：只有 local 开 header 假用户。显式 true/false 覆盖默认。
    allow_header_auth: bool | None = None
    logto_endpoint: str = ""
    logto_audience: str = ""

    @property
    def header_auth_enabled(self) -> bool:
        if self.allow_header_auth is not None:
            return self.allow_header_auth
        return self.environment == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
