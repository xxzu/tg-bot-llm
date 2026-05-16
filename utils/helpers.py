"""
辅助函数模块
"""


async def prune_messages(messages, max_chars):
    """裁剪消息列表以适应最大字符数"""
    pruned_messages = []
    total_chars = 0

    for message in reversed(messages):
        content_length = len(message["content"])
        remaining_chars = max_chars - total_chars

        if remaining_chars <= 0:
            break

        if content_length > remaining_chars:
            pruned_content = message["content"][:remaining_chars]
            pruned_messages.append({"role": message["role"], "content": pruned_content})
            break

        pruned_messages.append(message)
        total_chars += content_length

    return list(reversed(pruned_messages))


async def generate_history(messages):
    """生成历史记录文本"""
    return "\n\n".join(f"{msg['role']}:\n{msg['content']}" for msg in messages)


async def send_history(bot, user_id, history):
    """发送历史记录"""
    from aiogram.utils.formatting import Text
    
    max_length = 4096
    lines = history.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1

        if current_length + line_length > max_length:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_length
        else:
            current_chunk.append(line)
            current_length += line_length

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    for chunk in chunks:
        content_kwargs = Text(chunk)
        await bot.send_message(
            user_id,
            **content_kwargs.as_kwargs(),
            disable_web_page_preview=True,
        )
