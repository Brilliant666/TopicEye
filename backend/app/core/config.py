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
    ADMIN_SEED_ENABLED: bool = False
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_DISPLAY_NAME: Optional[str] = None
    APP_SECRET_KEY: str = "topiceye-local-dev-secret-change-me"
    INTEGRATION_SECRET_KEY: Optional[str] = None
    SCHEDULER_ENABLED: bool = True
    CACHE_WARMUP_ENABLED: bool = True
    READ_CACHE_TTL_SECONDS: float = 60.0
    SOURCE_SYNC_TIMEOUT_SECONDS: int = 120
    SOURCE_SYNC_WORKER_CONCURRENCY: int = 3
    POST_SYNC_ANALYSIS_BATCH_SIZE: int = 10
    POST_SYNC_ANALYSIS_TIME_BUDGET_SECONDS: int = 520
    POST_SYNC_MIN_REMAINING_SECONDS: int = 90
    CREATION_PLAN_TIMEOUT_SECONDS: int = 45
    WEREAD_SKILL_API_URL: Optional[str] = None

    # ── Agent config ──
    AGENT_MAX_STEPS: int = 10
    AGENT_TEMPERATURE: float = 0.3
    AGENT_MAX_RETRIES: int = 3

    # ── Rate limiting ──
    LLM_REQUESTS_PER_MINUTE: int = 60
    LLM_TOKENS_PER_MINUTE: int = 100000
    LLM_WORKER_CONCURRENCY: int = 4
    ANALYSIS_WORKER_CONCURRENCY: int = 3
    ANALYSIS_JOB_INFLIGHT_TTL_SECONDS: int = 900
    ANALYSIS_CASCADE_ENABLED: bool = False
    ANALYSIS_LITE_ROUTING_GROUP: str = "analysis_lite"
    ANALYSIS_PRO_ROUTING_GROUP: str = "default"
    ANALYSIS_CASCADE_ESCALATE_SCORE: float = 75.0
    ANALYSIS_CASCADE_MIN_CONFIDENCE: float = 0.75
    ENRICHMENT_WORKER_CONCURRENCY: int = 3
    CLASSIFICATION_WORKER_CONCURRENCY: int = 3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
