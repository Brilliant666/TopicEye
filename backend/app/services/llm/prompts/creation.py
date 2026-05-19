"""
Creation prompts — extracted from app.services.creation.

Used by:
    - app.services.creation.generate_creation_plan
"""

PLATFORM_PROMPTS = {
    "xiaohongshu": {
        "name": "小红书图文",
        "instruction": """你是一个小红书爆款内容策划师。基于以下素材，生成小红书图文创作方案。

要求：
- 标题：3个备选，用数字/对比/悬念吸引点击，≤20字
- 封面文案：1句核心slogan，≤15字
- 正文结构：开头hook(1句话抓注意力) + 3-5个要点(每个要点含emoji+一句话) + 结尾互动引导
- 话题标签：5-8个热门标签
- 风格要求：口语化、有情绪共鸣、适当用emoji但不过度

输出JSON格式：
{
  "titles": ["标题1", "标题2", "标题3"],
  "cover_slogan": "封面文案",
  "structure": {
    "hook": "开头hook",
    "points": ["要点1", "要点2", "要点3"],
    "cta": "结尾互动引导"
  },
  "tags": ["标签1", "标签2"],
  "tone": "建议语气/风格"
}""",
    },
    "short_video": {
        "name": "短视频脚本",
        "instruction": """你是一个短视频脚本策划师。基于以下素材，生成60秒短视频脚本。

要求：
- 标题：3个备选，适合抖音/B站，≤25字
- 开头3秒hook：用冲突/悬念/数据一句话留住观众
- 正文：分3-4个镜头，每个镜头包含画面描述+旁白文案
- 结尾：互动引导(点赞/关注/评论)
- 时长分配：每个镜头标注建议秒数

输出JSON格式：
{
  "titles": ["标题1", "标题2", "标题3"],
  "total_seconds": 60,
  "scenes": [
    {
      "seq": 1,
      "seconds": 3,
      "visual": "画面描述",
      "narration": "旁白文案"
    }
  ],
  "hook": "开头3秒hook文案",
  "cta": "结尾互动引导",
  "bgm_suggestion": "背景音乐建议"
}""",
    },
    "wechat": {
        "name": "公众号长文",
        "instruction": """你是一个公众号爆款文章策划师。基于以下素材，生成公众号长文大纲。

要求：
- 标题：3个备选，适合公众号，可适当长一点但≤30字
- 结构：5-7个小节，每节含标题+核心论点+支撑素材(数据/案例/引用)
- 开头：用故事/数据/痛点引入
- 结尾：金句总结+行动号召
- 适合插入的配图位置标注

输出JSON格式：
{
  "titles": ["标题1", "标题2", "标题3"],
  "outline": [
    {
      "section": 1,
      "heading": "小节标题",
      "points": ["论点1", "论点2"],
      "evidence": "支撑素材建议",
      "image_hint": "配图建议(如需要)"
    }
  ],
  "opening": "开头引入方式",
  "closing": "结尾金句",
  "word_count_estimate": 2000,
  "key_quote": "文内可引用的金句"
}""",
    },
}
