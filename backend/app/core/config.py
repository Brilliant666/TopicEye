from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Database ──
    DATABASE_URL: str = "sqlite+aiosqlite:///./topiceye.db"
    DATABASE_SQLITE_DOMAIN_SPLIT_ENABLED: bool = False
    DATABASE_SQLITE_DOMAIN_DIR: str = "./data/domains"
    # DuckDB connects in-memory and ATTACHes the configured OLTP database
    # READ_ONLY. SQLite and PostgreSQL are both supported as DuckDB sources.
    DUCKDB_THREADS: int = 2
    DUCKDB_MEMORY_LIMIT: str = "256MB"
    DUCKDB_EXTENSION_DIR: str = "./data/duckdb_extensions"

    # ── Startup behavior ──
    AUTO_CREATE_TABLES_ON_STARTUP: bool = True
    STARTUP_SEED_ENABLED: bool = True
    ADMIN_SEED_ENABLED: bool = True
    ADMIN_EMAIL: str = "admin@topiceye.local"
    ADMIN_PASSWORD: str = "TopicEyeAdmin123!"
    ADMIN_DISPLAY_NAME: str = "TopicEye 管理员"
    SCHEDULER_ENABLED: bool = True
    CACHE_WARMUP_ENABLED: bool = True
    READ_CACHE_TTL_SECONDS: float = 60.0
    SOURCE_SYNC_TIMEOUT_SECONDS: int = 120
    CREATION_PLAN_TIMEOUT_SECONDS: int = 45
    WEREAD_SKILL_API_URL: Optional[str] = None

    # ── Legacy DeepSeek config (backward compatible) ──
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # ── Primary LLM provider ──
    LLM_PROVIDER: str = "deepseek"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = "deepseek/deepseek-chat"

    # ── Fallback LLM provider (MiniMax or other) ──
    LLM_FALLBACK_ENABLED: bool = False
    LLM_FALLBACK_PROVIDER: Optional[str] = None
    LLM_FALLBACK_API_KEY: Optional[str] = None
    LLM_FALLBACK_BASE_URL: Optional[str] = None
    LLM_FALLBACK_MODEL: Optional[str] = None

    # ── MiniMax provider ──
    MINIMAX_API_KEY: Optional[str] = None
    MINIMAX_MODEL: str = "minimax/MiniMax-Text-01"
    MINIMAX_ENABLED: bool = False

    # ── Agent config ──
    AGENT_MAX_STEPS: int = 10
    AGENT_TEMPERATURE: float = 0.3
    AGENT_MAX_RETRIES: int = 3

    # ── Rate limiting ──
    LLM_REQUESTS_PER_MINUTE: int = 60
    LLM_TOKENS_PER_MINUTE: int = 100000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def get_primary_model(self) -> str:
        """Return the primary model string for litellm."""
        if self.LLM_MODEL:
            return self.LLM_MODEL
        return f"{self.LLM_PROVIDER}/{self.LLM_MODEL}"

    def get_primary_api_key(self) -> Optional[str]:
        """Return API key for primary provider."""
        return self.LLM_API_KEY or self.DEEPSEEK_API_KEY

    def get_primary_base_url(self) -> Optional[str]:
        """Return base URL for primary provider."""
        return self.LLM_BASE_URL

    def get_fallback_model(self) -> Optional[str]:
        """Return the fallback model string for litellm."""
        if not self.LLM_FALLBACK_ENABLED and not self.MINIMAX_ENABLED:
            return None
        if self.MINIMAX_ENABLED and self.MINIMAX_API_KEY:
            return self.MINIMAX_MODEL
        if self.LLM_FALLBACK_MODEL:
            return self.LLM_FALLBACK_MODEL
        return None

    def get_fallback_api_key(self, model: str) -> Optional[str]:
        """Return API key for fallback provider based on model name."""
        if "minimax" in model.lower() and self.MINIMAX_API_KEY:
            return self.MINIMAX_API_KEY
        return self.LLM_FALLBACK_API_KEY

    def get_fallback_base_url(self, model: str) -> Optional[str]:
        """Return base URL for fallback provider."""
        if "minimax" in model.lower():
            return None  # MiniMax uses default litellm endpoint
        return self.LLM_FALLBACK_BASE_URL


settings = Settings()
