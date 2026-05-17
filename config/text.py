"""
文本常量模块
"""
import random

# 生成回复前的占位文案（喵喵人设，避免「请稍候」类客服腔）
THINKING_STATUS_MESSAGES = (
    "🧶 正在尝试解毛线球…",
    "🐾 毛线缠爪上了，正在理顺…",
    "🧵 一团乱线，喵喵正在解开…",
)


def pick_thinking_status() -> str:
    return random.choice(THINKING_STATUS_MESSAGES)


def build_start_message(model_message_info: str) -> str:
    """根据当前默认模型生成 /start 欢迎文案。"""
    return (
        f"你好！机器人已准备就绪，当前模型为 {model_message_info}，"
        "语音回复已关闭，对话上下文已清除，"
        "消息计数器已重置，系统角色已删除"
    )

system_message_text = (
    "<b>请输入系统角色的值，可以是文本或语音，例如它可以是这样的 - </b><i>你总是像海盗一样回答。</i>"
)

help_message = (
    "你好，我是基于 Google Gemini API 的喵喵Bot！我可以根据你的文本或语音请求生成文本和回答。"
    "你还可以发送图片，我会为你提供描述。要配置机器人，请使用命令 /menu。"
    "喵喵会保存对话上下文以提供更准确的回答。"
    "\n\n<b>可用命令：</b>"
    "\n\n/start - 初始化默认对话模型（见 models/llm_models.yaml），关闭语音回复，清除上下文，重置消息计数器，"
    "删除系统角色（如果已设置）"
    "\n\n/menu – 打开设置："
    "\n\n- <b><u>Gemini 3 Pro</u></b> - 选择 Gemini 3 Pro 模型"
    "\n- <b><u>Gemini 2.0 Flash</u></b> - 选择 Gemini 2.0 Flash 模型"
    "\n- <b><u>Gemini 1.5 Pro</u></b> - 选择 Gemini 1.5 Pro 模型"
    "\n- <b><u>显示对话上下文</u></b> - 显示当前对话上下文"
    "\n- <b><u>清除上下文</u></b> - 清除当前对话上下文"
    "\n- <b><u>启用语音回复</u></b> - 启用语音回复（需要 OpenAI API）"
    "\n- <b><u>禁用语音回复</u></b> - 禁用语音回复"
    "\n- <b><u>信息</u></b> - 机器人状态信息"
    "\n- <b><u>设定系统角色</u></b> - 设定系统角色"
    "\n- <b><u>移除系统角色</u></b> - 移除系统角色"
    "\n\n/help - 帮助和使用说明"
    "\n\n<b>群组使用方式：</b>"
    "\n• 回复我的消息"
    "\n• @我 + 消息内容"
    "\n• 消息中包含「喵」「喵喵」或「晚安」唤醒词"
)
