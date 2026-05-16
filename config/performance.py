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

# 关键词判定为 spam/广告 后自动禁言小时数；0 表示不自动禁言
SPAM_AUTO_MUTE_HOURS = int(os.getenv("SPAM_AUTO_MUTE_HOURS", "24"))

# 群聊使用 OpenAI function calling 执法（替代 @@MOD 文本协议）
GROUP_MOD_TOOLS_ENABLED = os.getenv("GROUP_MOD_TOOLS_ENABLED", "1").strip() not in (
    "0",
    "false",
    "False",
)
