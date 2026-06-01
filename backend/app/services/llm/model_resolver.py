"""LiteLLM model name resolution helpers."""

from __future__ import annotations

from typing import Optional, Protocol


class ModelLike(Protocol):
    provider: str
    model_id: str
    api_base: Optional[str]


OPENAI_COMPATIBLE_PROVIDER = {"openai", "custom", "deepseek", "minimax", "zhipu"}


def resolve_litellm_model(model: ModelLike) -> str:
    """Return a LiteLLM model string that includes a provider when needed."""
    model_id = (model.model_id or "").strip()
    provider = (model.provider or "").strip().lower()
    api_base = model.api_base or ""

    if "opencode.ai/zen" in api_base and model_id.startswith("opencode/"):
        return f"openai/{model_id.removeprefix('opencode/')}"

    if "/" in model_id and not (api_base and provider in OPENAI_COMPATIBLE_PROVIDER):
        return model_id

    if "open.bigmodel.cn" in api_base:
        return f"openai/{model_id}"

    if api_base and provider in OPENAI_COMPATIBLE_PROVIDER:
        if model_id.startswith("openai/"):
            return model_id
        return f"openai/{model_id}"

    if provider:
        return f"{provider}/{model_id}"

    return model_id
