from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_MODEL_PARAMETERS: dict[str, Any] = {
    "routing_group": "default",
    "routing_priority": 100,
    "cooldown_seconds": 300,
    "temperature": 0.3,
    "max_tokens": 2000,
    "requests_per_minute": 30,
    "enabled": True,
}


MODEL_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "key": "openai_fast",
        "label": "OpenAI 通用快模型",
        "provider": "openai",
        "model_id": "gpt-4.1-mini",
        "api_base": None,
        "model_family": "openai",
        "channel_name": "official",
        "description": "适合日常创作方案、摘要和轻量分析，稳定优先。",
        "recommended_for": ["创作方案", "摘要生成", "轻量分析"],
        "requires": ["api_key"],
        "help": "只需要填写 OpenAI API Key；其他参数可以先保持默认。",
        "defaults": {
            **DEFAULT_MODEL_PARAMETERS,
            "name": "OpenAI 通用快模型",
            "cost_per_1m_input": None,
            "cost_per_1m_input_cache_hit": None,
            "cost_per_1m_output": None,
        },
    },
    {
        "key": "deepseek_balanced",
        "label": "DeepSeek 性价比模型",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "api_base": None,
        "model_family": "deepseek",
        "channel_name": "official",
        "description": "适合高频内容处理和个人工作流，成本敏感时优先选它。",
        "recommended_for": ["高频生成", "内容分析", "日常工作流"],
        "requires": ["api_key"],
        "help": "填写 DeepSeek API Key 即可。RPM 默认较保守，避免个人 Key 被高并发打满。",
        "defaults": {
            **DEFAULT_MODEL_PARAMETERS,
            "name": "DeepSeek 性价比模型",
            "requests_per_minute": 20,
            "cost_per_1m_input": 1,
            "cost_per_1m_input_cache_hit": 0.02,
            "cost_per_1m_output": 2,
        },
    },
    {
        "key": "openai_compatible",
        "label": "OpenAI 兼容网关",
        "provider": "openai",
        "model_id": "",
        "api_base": "https://api.example.com/v1",
        "model_family": None,
        "channel_name": "custom_gateway",
        "description": "适合 OpenRouter、OpenCode、智谱等兼容 OpenAI 格式的网关。",
        "recommended_for": ["自定义网关", "国内兼容渠道", "备用模型"],
        "requires": ["api_key", "api_base", "model_id"],
        "help": "Provider 保持 OpenAI，填写网关的 API Base、API Key 和模型名即可。",
        "defaults": {
            **DEFAULT_MODEL_PARAMETERS,
            "name": "OpenAI 兼容网关",
            "requests_per_minute": 15,
        },
    },
    {
        "key": "custom",
        "label": "完全自定义",
        "provider": "custom",
        "model_id": "",
        "api_base": None,
        "model_family": None,
        "channel_name": None,
        "description": "适合熟悉 LiteLLM 路由和供应商参数的高级用户。",
        "recommended_for": ["高级配置", "特殊供应商"],
        "requires": ["provider", "model_id"],
        "help": "如果不确定怎么填，优先使用上面的推荐预设。",
        "defaults": {
            **DEFAULT_MODEL_PARAMETERS,
            "name": "自定义模型",
            "requests_per_minute": 10,
        },
    },
)


def list_model_presets() -> dict[str, Any]:
    return {
        "defaults": deepcopy(DEFAULT_MODEL_PARAMETERS),
        "presets": [deepcopy(item) for item in MODEL_PRESETS],
        "help": {
            "beginner_tip": "新用户优先选择推荐预设，只填写 API Key；模型参数后续再微调。",
            "rpm_tip": "RPM 是每分钟请求数。个人 Key 建议先用 10-30，避免同步高峰触发供应商限流。",
            "temperature_tip": "Temperature 越低越稳定。选题分析和摘要建议 0.2-0.4。",
            "max_tokens_tip": "Max Tokens 控制单次输出长度。创作方案建议 2000 起步。",
        },
    }


def get_model_preset(key: str | None) -> dict[str, Any] | None:
    normalized = (key or "").strip().lower()
    if not normalized:
        return None
    for preset in MODEL_PRESETS:
        if preset["key"] == normalized:
            return deepcopy(preset)
    return None


def apply_model_preset(payload: dict[str, Any], preset_key: str | None) -> dict[str, Any]:
    preset = get_model_preset(preset_key)
    if preset is None:
        return payload

    defaults = {
        **preset.get("defaults", {}),
        "provider": preset.get("provider"),
        "model_id": preset.get("model_id"),
        "api_base": preset.get("api_base"),
        "model_family": preset.get("model_family"),
        "channel_name": preset.get("channel_name"),
        "description": preset.get("description"),
    }
    return {
        key: value
        for key, value in {**defaults, **payload}.items()
        if value is not None
    }
