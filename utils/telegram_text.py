"""
发往 Telegram 的文本校验（避免 message text is empty）。
"""
from utils.markdown import has_markdown, markdown_to_html

# 模型无正文时的兜底回复
EMPTY_REPLY_FALLBACK = "喵，线团缠死了，这次没理出话来。你换一句再 @ 我试试？"


def ensure_telegram_text(text: str | None) -> str:
    cleaned = (text or "").strip()
    return cleaned if cleaned else EMPTY_REPLY_FALLBACK


def prepare_telegram_body(text: str | None) -> tuple[str, str | None]:
    """
    返回 (正文, parse_mode)。
    parse_mode 为 None 表示纯文本；为 "HTML" 时使用 HTML。
    正文保证非空。
    """
    plain = ensure_telegram_text(text)
    if has_markdown(plain):
        html = markdown_to_html(plain).strip()
        if html:
            return html, "HTML"
    return plain, None
