"""
群聊图片视觉审核（与私聊「描述图片」分离）。
"""
import os

GROUP_IMAGE_MOD_ENABLED = os.getenv("GROUP_IMAGE_MOD_ENABLED", "1").strip() not in (
    "0",
    "false",
    "False",
)

# 模型判定 violation=true 且 confidence >= 该值才处置
GROUP_IMAGE_VIOLATION_CONFIDENCE = float(
    os.getenv("GROUP_IMAGE_VIOLATION_CONFIDENCE", "0.72")
)

# 诈骗类累计警告达此次数则封禁（与文档「3 次」一致）
GROUP_IMAGE_SCAM_WARN_BAN = int(os.getenv("GROUP_IMAGE_SCAM_WARN_BAN", "3"))

# 覆盖 llm_models.yaml 的 default_vision_model_id（仅群审图）
# GROUP_VISION_MODEL_ID=nvidia/nemotron-nano-12b-v2-vl:free

GROUP_IMAGE_MODERATION_PROMPT = """你是 Telegram 群聊的图片审核员，只判断图片是否违规，不要描述画面、不要闲聊。

结合图片与附图说明（若有），判断是否属于以下任一违规：
- 广告推广、引流、加群、代购、刷单兼职
- 二维码/链接引流、虚假中奖、投资理财诈骗
- 色情、裸露、招嫖
- 赌博、违禁品

只输出一行 JSON，不要 markdown，不要其它文字：
{{"violation":true或false,"type":"spam|scam|porno|gambling|other|none","confidence":0到1的小数,"reason":"不超过30字的中文"}}

附图说明：{caption}
"""
