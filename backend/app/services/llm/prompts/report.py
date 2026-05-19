"""
Report prompts — extracted from app.services.daily_report.

Used by:
    - app.services.daily_report.generate_daily_report
"""

REPORT_PROMPT = """你是一位资深内容策划顾问。请根据以下今日精选内容数据，生成一份面向创作者的每日选题简报。

## 今日内容数据（{date}）
{items_text}

## 请严格按以下 JSON 格式输出：
{{
  "overview": "一段200字以内的今日热点概述，用轻松专业的口吻，点出今日最值得关注的方向",
  "takeaway": "一句话核心要点，适合作为日报标题/推送文案",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "trends": [
    {{"title": "趋势标题", "desc": "趋势描述（30字内）", "color": "#3B82F6"}}
  ],
  "top_picks": [
    {{"title": "选题标题", "reason": "推荐理由（40字内）", "score": 85, "platforms": ["公众号", "小红书"]}}
  ],
  "platform_tips": {{
    "公众号": ["tip1"],
    "小红书": ["tip1"],
    "视频号": ["tip1"]
  }}
}}

要求：
- trends 给出 2-3 个今日内容趋势
- top_picks 从上面数据中选 3-5 个最值得写的选题
- platform_tips 给出各平台今天的创作建议
- 所有文本用中文
- 只输出 JSON，不要其他内容"""
