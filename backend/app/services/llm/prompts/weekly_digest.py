"""
Weekly Digest LLM prompts — extracted for maintainability.

Used by:
    - app.services.weekly_digest.generate_weekly_digest
"""

WEEKLY_DIGEST_PROMPT = """你是一位资深内容策划顾问。请根据以下本周精选内容数据，生成一份面向创作者的「精选周刊」。

## 本周内容数据（{week_label}）
{items_text}

## 本周分类统计
{category_text}

## 请严格按以下 JSON 格式输出：
{{
  "overview": "一段300字以内的本周热点概述，用专业且有洞察力的口吻，梳理本周最值得关注的内容趋势和行业动态",
  "takeaway": "一句话核心要点，适合作为周刊标题/推送文案",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5", "关键词6"],
  "trends": [
    {{"title": "趋势标题", "desc": "趋势描述（50字内）", "color": "#3B82F6", "momentum": "up"}}
  ],
  "top_picks": [
    {{"rank": 1, "title": "选题标题", "source": "来源名称", "category": "分类", "reason": "推荐理由（60字内）", "score": 85, "platforms": ["公众号", "小红书"]}}
  ],
  "category_summary": {{
    "AI": {{"count": 5, "avg_score": 78, "top_title": "最热标题"}},
    "产品": {{"count": 3, "avg_score": 72, "top_title": "最热标题"}}
  }},
  "platform_tips": {{
    "公众号": ["本周创作建议1", "本周创作建议2"],
    "小红书": ["本周创作建议1", "本周创作建议2"],
    "视频号": ["本周创作建议1", "本周创作建议2"],
    "抖音": ["本周创作建议1"]
  }},
  "topic_clusters": [
    {{"name": "话题名称", "count": 5, "heat": 90, "representative_title": "代表文章标题"}}
  ],
  "action_items": [
    {{"title": "建议选题", "angle": "切入角度（30字内）", "difficulty": "简单/中等/困难", "platform": "推荐平台"}}
  ]
}}

要求：
- trends 给出 3-5 个本周内容趋势，momentum 为 up/down/stable
- top_picks 从上面数据中选 8-10 个最值得写的选题，按推荐度排序
- category_summary 按分类统计本周内容（count=数量, avg_score=平均创作分, top_title=该分类最热内容）
- platform_tips 给出各平台本周的创作建议（每平台2-3条）
- topic_clusters 识别 3-6 个热门话题聚类
- action_items 给出 5-8 个可执行的创作建议，difficulty 为简单/中等/困难
- 所有文本用中文
- 只输出 JSON，不要其他内容"""
