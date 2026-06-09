"""
LLM service sub-package.

Re-exports the public API so that existing imports continue to work:

    from app.services.llm import call_llm, call_llm_json
"""

from app.services.llm.provider import call_llm, call_llm_json, call_llm_json_with_metadata  # noqa: F401

__all__ = ["call_llm", "call_llm_json", "call_llm_json_with_metadata"]
