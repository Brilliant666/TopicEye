from types import SimpleNamespace

from app.api.v1.llm_models import (
    _auto_score_response,
    _resolve_litellm_model,
    _sample_payload,
)
from app.services.llm.model_resolver import resolve_litellm_model


def test_resolve_litellm_model_adds_provider_prefix_for_plain_model_id():
    model = SimpleNamespace(provider="deepseek", model_id="deepseek-chat", api_base=None)

    assert _resolve_litellm_model(model) == "deepseek/deepseek-chat"


def test_resolve_litellm_model_uses_openai_prefix_for_bigmodel_endpoint():
    model = SimpleNamespace(
        provider="zai",
        model_id="glm-5.1",
        api_base="https://open.bigmodel.cn/api/paas/v4",
    )

    assert _resolve_litellm_model(model) == "openai/glm-5.1"


def test_shared_model_resolver_preserves_already_prefixed_model_id():
    model = SimpleNamespace(provider="deepseek", model_id="deepseek/deepseek-chat", api_base=None)

    assert resolve_litellm_model(model) == "deepseek/deepseek-chat"


def test_sample_payload_parses_title_and_content_from_json():
    sample = _sample_payload('{"title":"标题","content":"正文"}')

    assert sample == {"title": "标题", "content": "正文"}


def test_auto_score_accepts_fenced_json_and_json_lists():
    assert _auto_score_response('```json\n{"summary":"ok","tags":["a"]}\n```') >= 4
    assert _auto_score_response('[{"title":"a"}]') >= 3
