"""
对话历史：API 请求侧滑动窗口（与持久化 messages 解耦，仅影响下发给模型的内容）。
"""

# 最近 N 轮（每轮 user + assistant 各一条，共 2N 条）
MAX_CONTEXT_ROUNDS = 5


def slice_messages_for_api(messages: list) -> list:
    """
    从完整 messages 中取「发给模型」的历史片段。

    约定：调用方在追加当前 user 后传入的 messages 最后一项为当前用户输入；
    则历史为 messages[:-1]，只取最近 MAX_CONTEXT_ROUNDS 轮。
    """
    if not messages:
        return []
    history = messages[:-1]
    cap = MAX_CONTEXT_ROUNDS * 2
    if len(history) <= cap:
        return list(history)
    return history[-cap:]
