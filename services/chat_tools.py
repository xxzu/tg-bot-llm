"""
OpenAI function calling（实现已迁至 services.llm，此处保留兼容导入）。
"""
from services.llm.adapters.openai_compat import complete_with_tools as chat_completions_with_tools
from services.llm.invoker import get_invoker
from services.llm.messages import build_chat_messages as build_messages_payload
from services.llm.types import LLMChatRequest
from services.moderation_tools import ModerationToolContext

__all__ = [
    "build_messages_payload",
    "chat_completions_with_tools",
    "generate_with_group_tools",
]


async def generate_with_group_tools(
    user_data,
    prompt: str,
    system_instruction: str,
    model: str,
    provider: str,  # noqa: ARG001 — 已由 model_id 在 registry 解析
    tool_ctx: ModerationToolContext,
) -> str:
    invoker = get_invoker()
    request = LLMChatRequest(
        model_id=model,
        user_data=user_data,
        prompt=prompt,
        system_instruction=system_instruction,
    )
    return await invoker.chat_with_tools(request, tool_ctx)
