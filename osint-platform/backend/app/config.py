"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "OSINT Platform"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = "sqlite+aiosqlite:///./data/osint.db"

    user_agent: str = "OSINT-Platform/1.0 (+https://example.com/bot)"
    request_timeout: int = 10
    max_crawl_depth: int = 1
    max_pages_per_search: int = 15
    rate_limit_per_minute: int = 30
    respect_robots_txt: bool = True

    serpapi_key: str = ""
    hibp_api_key: str = ""

    # --- Elasticsearch (internal intelligence layer) ---
    es_enabled: bool = False
    es_url: str = "https://localhost:9200"
    es_user: str = "elastic"
    es_password: str = ""
    es_index: str = "tc_index"
    es_verify_certs: bool = False
    es_ca_cert: str = ""
    es_timeout: int = 8
    es_max_hits: int = 25

    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
