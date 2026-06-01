from app.services.daily_report import REPORT_PROMPT as ACTIVE_DAILY_REPORT_PROMPT
from app.services.llm.prompts.analysis import ANALYSIS_PROMPT, ANALYSIS_PROMPT_EN, SYSTEM_PROMPT_EN
from app.services.llm.prompts.monthly_digest import MONTHLY_DIGEST_PROMPT
from app.services.llm.prompts.report import REPORT_PROMPT as LEGACY_DAILY_REPORT_PROMPT
from app.services.llm.prompts.weekly_digest import WEEKLY_DIGEST_PROMPT


def test_analysis_recommendation_is_required_as_chinese_summary():
    assert "中文摘要式推荐理由" in ANALYSIS_PROMPT
    assert "不要英文" in ANALYSIS_PROMPT
    assert "all output text must be Chinese" in SYSTEM_PROMPT_EN
    assert "中文摘要式推荐理由" in ANALYSIS_PROMPT_EN
    assert "不要输出英文" in ANALYSIS_PROMPT_EN


def test_report_top_pick_reasons_are_required_as_chinese_summaries():
    prompts = [
        ACTIVE_DAILY_REPORT_PROMPT,
        LEGACY_DAILY_REPORT_PROMPT,
        WEEKLY_DIGEST_PROMPT,
        MONTHLY_DIGEST_PROMPT,
    ]

    for prompt in prompts:
        assert "中文摘要式推荐理由" in prompt
        assert "先概括这条内容讲了什么" in prompt
        assert "不要输出英文" in prompt
