"""Environment bootstrap for isolated Rardar LLM control tests."""

from __future__ import annotations

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://rardar_llm_test:rardar_llm_test@127.0.0.1:59999/rardar_llm_test",
)
