"""
对话性能相关配置（可通过 .env 覆盖）
"""
import os

# 群聊短回复场景下的输出 token 上限（显著缩短生成时间）
CHAT_MAX_OUTPUT_TOKENS = int(os.getenv("CHAT_MAX_OUTPUT_TOKENS", "768"))

# 1=关闭 NVIDIA 深度思考（群聊强烈建议开启）
NVIDIA_DISABLE_THINKING = os.getenv("NVIDIA_DISABLE_THINKING", "1").strip() not in (
    "0",
    "false",
    "False",
)

# 流式回复时编辑 Telegram 消息的最小间隔（秒）；首包不受此限制
STREAM_EDIT_INTERVAL_SEC = float(os.getenv("STREAM_EDIT_INTERVAL_SEC", "0.35"))

# 同一用户在本群累计「广告警告」达此次数后踢出/封禁（默认 3，每次命中先发警告）
SPAM_BAN_THRESHOLD = int(os.getenv("SPAM_BAN_THRESHOLD", "3"))
# 广告警告满额后的处置：kick=踢出可再加群，ban=封禁
SPAM_ESCALATE_ACTION = os.getenv("SPAM_ESCALATE_ACTION", "kick").strip().lower()

# 群聊使用 OpenAI function calling 执法（替代 @@MOD 文本协议）
GROUP_MOD_TOOLS_ENABLED = os.getenv("GROUP_MOD_TOOLS_ENABLED", "1").strip() not in (
    "0",
    "false",
    "False",
)

# 贝叶斯广告识别（参考 bayes_spam_sniper）
BAYES_SPAM_ENABLED = os.getenv("BAYES_SPAM_ENABLED", "1").strip() not in (
    "0",
    "false",
    "False",
)
BAYES_SPAM_THRESHOLD = float(os.getenv("BAYES_SPAM_THRESHOLD", "0.94"))
BAYES_CHINESE_SPACE_THRESHOLD = float(os.getenv("BAYES_CHINESE_SPACE_THRESHOLD", "0.8"))
BAYES_SHORT_MESSAGE_WORD_THRESHOLD = int(os.getenv("BAYES_SHORT_MESSAGE_WORD_THRESHOLD", "3"))
