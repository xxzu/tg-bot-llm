"""
将 Telegram 回复引用链中的被引用消息格式化为模型可读上下文。
"""
from typing import Optional

from aiogram.types import Message

# 单条引用正文上限，避免撑爆上下文
MAX_QUOTE_CHARS = 3500


def _text_body(reply: Message) -> str:
    if reply.text:
        return reply.text.strip()
    if reply.caption:
        return reply.caption.strip()
    if reply.photo:
        return "[图片消息，无文字说明]"
    if reply.voice or reply.audio or reply.video_note:
        return "[语音/音频消息，无转写文本]"
    if reply.video:
        return "[视频消息，无配文]"
    if reply.sticker:
        return "[贴纸]"
    if reply.document:
        name = reply.document.file_name or "文件"
        return f"[文件: {name}]"
    if reply.poll:
        return f"[投票: {reply.poll.question}]"
    return "[该消息无可用文字内容]"


def format_reply_context(reply: Message) -> Optional[str]:
    """将被回复消息格式化为一段中文标注的引用块；无法获取时返回 None。"""
    if reply is None:
        return None
    try:
        sender = reply.from_user.full_name if reply.from_user else "未知用户"
        uname = reply.from_user.username if reply.from_user else None
        if uname:
            sender = f"{sender} (@{uname})"
        body = _text_body(reply)
        if len(body) > MAX_QUOTE_CHARS:
            body = body[:MAX_QUOTE_CHARS] + "\n...(引用内容已截断)"
        block = (
            "[用户正在回复以下群消息，请结合引用内容理解问题]\n"
            f"引用发送者: {sender}\n"
            f"引用内容:\n{body}\n"
            "[引用结束]"
        )
        return block
    except Exception:
        return None


def merge_prompt_with_reply_context(base_prompt: str, reply: Optional[Message]) -> str:
    """若有引用消息，把引用块拼在用户问题前。"""
    ctx = format_reply_context(reply) if reply else None
    base = (base_prompt or "").strip()
    if not ctx:
        return base
    if base:
        return f"{ctx}\n\n用户说：\n{base}"
    return ctx
