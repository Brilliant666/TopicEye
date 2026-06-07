from types import SimpleNamespace

from app.api.v1.llm_models import (
    LLM_COMPLETION_TIMEOUT_SECONDS,
    ModelCreateRequest,
    ModelUpdateRequest,
    _auto_score_response,
    _completion_kwargs,
    _missing_explicit_api_key,
    _resolve_litellm_model,
    _sample_payload,
)
from app.services.llm.model_resolver import resolve_litellm_model


def test_resolve_litellm_model_adds_provider_prefix_for_plain_model_id():
    model = SimpleNamespace(provider="deepseek", model_id="deepseek-chat", api_base=None)

    assert _resolve_litellm_model(model) == "deepseek/deepseek-chat"


def test_resolve_litellm_model_uses_openai_prefix_for_bigmodel_endpoint():
    model = SimpleNamespace(
        provider="openai",
        model_id="glm-5.1",
        api_base="https://open.bigmodel.cn/api/paas/v4",
    )

    assert _resolve_litellm_model(model) == "openai/glm-5.1"


def test_shared_model_resolver_preserves_already_prefixed_model_id():
    model = SimpleNamespace(provider="deepseek", model_id="deepseek/deepseek-chat", api_base=None)

    assert resolve_litellm_model(model) == "deepseek/deepseek-chat"


def test_shared_model_resolver_routes_opencode_zen_through_openai_compatible_provider():
    model = SimpleNamespace(
        provider="openai",
        model_id="deepseek-v4-flash-free",
        api_base="https://opencode.ai/zen/v1",
    )

    assert resolve_litellm_model(model) == "openai/deepseek-v4-flash-free"


def test_shared_model_resolver_prefers_explicit_litellm_model():
    model = SimpleNamespace(
        provider="custom",
        model_id="opencode/deepseek-v4-flash-free",
        api_base="https://opencode.ai/zen/v1",
        extra_params={"litellm_model": "openai/deepseek-v4-flash-free"},
    )

    assert resolve_litellm_model(model) == "openai/deepseek-v4-flash-free"


def test_completion_kwargs_passes_openai_compatible_timeout_and_endpoint():
    model = SimpleNamespace(
        api_key="test-key",
        api_base="https://opencode.ai/zen/v1",
        extra_params=None,
    )

    kwargs = _completion_kwargs(
        model,
        "openai/deepseek-v4-flash-free",
        [{"role": "user", "content": "hello"}],
        temperature=0.3,
        max_tokens=200,
    )

    assert kwargs["model"] == "openai/deepseek-v4-flash-free"
    assert kwargs["api_key"] == "test-key"
    assert kwargs["api_base"] == "https://opencode.ai/zen/v1"
    assert kwargs["timeout"] == LLM_COMPLETION_TIMEOUT_SECONDS


def test_completion_kwargs_merges_explicit_litellm_params():
    model = SimpleNamespace(
        api_key="test-key",
        api_base="https://example.test/v1",
        extra_params={
            "cost_per_1m_input_cache_hit": 0.02,
            "litellm_params": {
                "timeout": 10,
                "custom_llm_provider": "openai",
                "unsupported": "ignored",
            },
        },
    )

    kwargs = _completion_kwargs(
        model,
        "openai/custom-model",
        [{"role": "user", "content": "hello"}],
        temperature=0.3,
        max_tokens=200,
    )

    assert kwargs["timeout"] == 10
    assert kwargs["custom_llm_provider"] == "openai"
    assert "unsupported" not in kwargs


def test_model_config_normalizes_blank_api_key_and_endpoint():
    created = ModelCreateRequest(
        name="OpenCode",
        provider="custom",
        model_id="opencode/deepseek-v4-flash-free",
        api_key="   ",
        api_base="  https://opencode.ai/zen/v1  ",
        routing_group="   ",
        model_family="  deepseek ",
        channel_name=" opencode ",
    )
    updated = ModelUpdateRequest(api_key="  real-key  ", api_base="     ")

    assert created.api_key is None
    assert created.api_base == "https://opencode.ai/zen/v1"
    assert created.routing_group == "default"
    assert created.model_family == "deepseek"
    assert created.channel_name == "opencode"
    assert updated.api_key == "real-key"
    assert updated.api_base is None


def test_missing_explicit_api_key_treats_blank_values_as_missing():
    request = ModelCreateRequest(
        name="OpenCode",
        provider="custom",
        model_id="opencode/deepseek-v4-flash-free",
        api_key="   ",
        api_base="  https://opencode.ai/zen/v1  ",
    )
    model = SimpleNamespace(api_key=request.api_key, api_base=request.api_base)

    assert _missing_explicit_api_key(model) is True


def test_sample_payload_parses_title_and_content_from_json():
    sample = _sample_payload('{"title":"标题","content":"正文"}')

    assert sample == {"title": "标题", "content": "正文"}


def test_auto_score_accepts_fenced_json_and_json_lists():
    assert _auto_score_response('```json\n{"summary":"ok","tags":["a"]}\n```') >= 4
    assert _auto_score_response('[{"title":"a"}]') >= 3
