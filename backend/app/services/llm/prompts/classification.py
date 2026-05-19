"""
Classification prompts — LLM-driven content categorization.

Used by:
    - app.services.classifier (classify_async)
"""

SYSTEM_PROMPT = """你是一位内容分类专家。你的任务是根据内容的标题和摘要，判断它属于哪个领域分类。

分类规则：
1. 优先从已有分类列表中选择最匹配的
2. 如果已有分类都不合适，输出一个简洁的新分类名（2-4个字）
3. 新分类名必须是中文，简洁通用，能覆盖该领域的内容
4. 不要使用过于细分的子分类（如"AI绘画"应归为"AI"）
5. 同时提取3-5个最能代表该内容的关键词标签

输出必须严格是JSON格式，不要输出其他内容。"""

CLASSIFICATION_PROMPT = """请对以下内容进行分类。

已有分类列表：{categories}

标题：{title}
摘要：{summary}

请严格按以下JSON格式输出（不要输出任何其他内容）：
{{
  "category": "分类名称（从已有列表中选择，或给出新分类名）",
  "is_new_category": true或false（是否为新分类）,
  "tags": ["关键词1", "关键词2", "关键词3"],
  "confidence": 0.0到1.0（分类置信度）
}}"""
