"""Explicitly initialize or run one bounded Rardar News quick-read batch."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.core.config import settings
from app.core.database import async_session
from app.core.product_profile import is_rardar_product
from app.services.llm.provider_budget import ProviderBudgetLedger
from app.services.rardar_news_quickread import QUICK_READ_TASK_ID, enhance_hotspot_news


def _external_absolute(path: Path, parser: argparse.ArgumentParser) -> Path:
    if not path.is_absolute():
        parser.error("Budget data must use an absolute path outside the checkout")
    resolved = path.resolve(strict=False)
    checkout = Path(__file__).resolve().parents[2]
    if resolved.is_relative_to(checkout):
        parser.error("Budget data must use an absolute path outside the checkout")
    return resolved


async def _run(arguments: argparse.Namespace) -> int:
    if settings.is_production or not is_rardar_product():
        raise RuntimeError("Local RARDAR_PRODUCT_MODE=true is required")
    ledger = ProviderBudgetLedger(
        arguments.budget_path,
        arguments.run_id,
        task_id=QUICK_READ_TASK_ID,
        limit=arguments.limit,
    )
    ledger.snapshot()
    expected = {
        "RARDAR_LLM_TASK_ID": QUICK_READ_TASK_ID,
        "RARDAR_LLM_RUN_ID": arguments.run_id,
        "RARDAR_LLM_BUDGET_PATH": str(arguments.budget_path),
        "RARDAR_LLM_BUDGET_LIMIT": str(arguments.limit),
    }
    previous = {key: os.environ.get(key) for key in expected}
    try:
        os.environ.update(expected)
        async with async_session() as db:
            result = await enhance_hotspot_news(db, item_limit=arguments.item_limit)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {"completed", "degraded"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initialize-budget", "run"))
    parser.add_argument("--budget-path", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--item-limit", type=int, default=18)
    arguments = parser.parse_args()
    arguments.budget_path = _external_absolute(arguments.budget_path, parser)
    if arguments.action == "initialize-budget":
        ledger = ProviderBudgetLedger.initialize(
            arguments.budget_path,
            arguments.run_id,
            task_id=QUICK_READ_TASK_ID,
            limit=arguments.limit,
        )
        print(json.dumps(ledger.snapshot(), ensure_ascii=False, sort_keys=True))
        return 0
    return asyncio.run(_run(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
