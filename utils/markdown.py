"""
Markdown 转 HTML 工具模块
"""
import re


def markdown_to_html(text: str) -> str:
    """将 Markdown 格式转换为 HTML 格式（Telegram 支持）"""
    if not text:
        return text
    
    # 转义 HTML 特殊字符
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    # 代码块 ```code```
    text = re.sub(r'```(\w+)?\n?(.*?)```', r'<pre><code>\2</code></pre>', text, flags=re.DOTALL)
    
    # 行内代码 `code`
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # 粗体 **text** 或 __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 斜体 *text* 或 _text_
    text = re.sub(r'(?<!\*)\*([^*\n]+?)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!_)_([^_\n]+?)_(?!_)', r'<i>\1</i>', text)
    
    # 删除线 ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    
    # 链接 [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)
    
    # 标题 # Title
    text = re.sub(r'^### (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    
    return text


def has_markdown(text: str) -> bool:
    """检测文本是否包含 Markdown 语法"""
    if not text:
        return False
    
    # 检测常见的 Markdown 语法
    markdown_patterns = [
        r'\*\*.*?\*\*',  # 粗体 **text**
        r'__.*?__',      # 粗体 __text__
        r'(?<!\*)\*[^*]+\*(?!\*)',  # 斜体 *text*
        r'(?<!_)_[^_]+_(?!_)',  # 斜体 _text_
        r'`[^`]+`',      # 行内代码 `code`
        r'```',          # 代码块 ```
        r'\[.*?\]\(.*?\)',  # 链接 [text](url)
        r'^#{1,6}\s',    # 标题 # Title
        r'~~.*?~~',      # 删除线 ~~text~~
    ]
    
    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE | re.DOTALL):
            return True
    return False


def clean_text_for_tts(text: str) -> str:
    """清洗文本，去除 Markdown 符号，使其适合语音合成"""
    if not text:
        return text
    
    # 替换链接 [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # 去除代码块 ```code``` -> code
    text = re.sub(r'```(\w+)?\n?(.*?)```', r'\2', text, flags=re.DOTALL)
    
    # 去除行内代码 `code` -> code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # 去除粗体 **text** 或 __text__ -> text
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    
    # 去除斜体 *text* 或 _text_ -> text
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # 去除删除线 ~~text~~ -> text
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    
    # 去除标题 # Title -> Title
    text = re.sub(r'^#+\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    
    # 去除列表符号 - 或 *
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    
    # 去除多余的 Markdown 符号
    text = text.replace('*', '')
    text = text.replace('_', '')
    text = text.replace('#', '')
    text = text.replace('`', '')
    
    return text.strip()
