"""
回调处理器模块
处理按钮点击回调
"""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config.settings import OWNER_ID, formatted_datetime
from config.buttons import (
    keyboard,
    keyboard_pic,
    keyboard_voice,
    keyboard_nvidia,
    get_keyboard_openrouter,
)
from services.llm.registry import format_model_display, get_registry
from config.text import system_message_text
from models.database import (
    get_chat_settings_data,
    get_or_create_user_data,
    model_storage_ids,
    save_user_data,
)
from utils.helpers import generate_history, send_history
from config.settings import bot

router = Router()


from handlers.states import ChangeValueState


def _is_llm_model_select_callback(callback: CallbackQuery) -> bool:
    """仅匹配 llm_models.yaml 中注册的模型按钮，不含 nvidia_models 等子菜单入口。"""
    data = callback.data
    return bool(data and data in get_registry().models_by_callback)


def _model_storage_ids(callback_query: CallbackQuery) -> tuple[int, int]:
    """私聊用 user_id；群聊模型存在群组维度 (chat_id, chat_id)。"""
    msg = callback_query.message
    return model_storage_ids(
        callback_query.from_user.id, msg.chat.id, msg.chat.type
    )


async def _apply_llm_model_from_callback(
    callback_query: CallbackQuery,
    callback_data: str,
) -> bool:
    """根据 callback_data 从 llm_models.yaml 切换模型。成功返回 True。"""
    spec = get_registry().get_model_by_callback(callback_data)
    if not spec:
        return False

    storage_user_id, storage_chat_id = _model_storage_ids(callback_query)
    prov = get_registry().providers.get(spec.provider)
    provider_label = prov.label if prov else spec.provider

    user_data = await get_or_create_user_data(storage_user_id, storage_chat_id)
    user_data.model = spec.id
    user_data.max_out = 128000 if spec.provider == "gemini" else 16384
    user_data.model_message_info = spec.selection_label(provider_label)
    user_data.model_message_chat = ""
    await save_user_data(storage_user_id, storage_chat_id)

    await callback_query.message.edit_text(
        text=(
            f"✅ 已启用模型：<b>{user_data.model_message_info}</b>\n\n"
            f"<i>模型 ID: {spec.id}</i>"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback_query.answer()
    return True


# 功能列表文本
FEATURE_LIST_TEXT = """
<b>🤖 喵喵Bot 功能列表</b>

<b>━━━ 🎯 核心 AI 功能 ━━━</b>
• <b>文本对话</b> - 与 Gemini AI 多轮对话，支持上下文记忆
• <b>图片理解</b> - 私聊发图：AI 描述内容；群内新人/首图：视觉审图（违规删图+简短说明）
• <b>语音输入</b> - 发送语音消息，自动转文字后发给 AI
• <b>语音回复</b> - 可选开启 AI 回复的语音版本

<b>━━━ ⚙️ 模型切换 ━━━</b>
• <b>Gemini 3 Pro</b> - 最新最强模型
• <b>Gemini 2.0 Flash</b> - 快速响应模型
• <b>Gemini 1.5 Pro</b> - 稳定可靠模型

<b>━━━ 💬 对话管理 ━━━</b>
• <b>显示上下文</b> - 查看当前对话历史
• <b>清除上下文</b> - 清空对话历史重新开始
• <b>系统角色</b> - 自定义 AI 的角色/人设

<b>━━━ 👥 群组功能 ━━━</b>
• <b>唤醒词</b> - 消息含「喵」「喵喵」或「晚安」时响应
• <b>@机器人</b> - 在群组中 @机器人发消息
• <b>回复机器人</b> - 回复机器人的消息继续对话

<b>━━━ 🛡️ 群组管理（管理员）━━━</b>
• <code>/ban</code> - 封禁用户
• <code>/unban</code> - 解封用户  
• <code>/kick</code> - 踢出用户
• <code>/warn</code> - 警告用户
• <code>/mute [小时]</code> - 禁言用户
• <code>/del</code> - 删除消息
• <code>/stats</code> - 查看违规统计
• <code>/ignore</code> - 忽略用户（不回复）
• <code>/unignore</code> - 取消忽略
• <code>/ignorelist</code> - 忽略列表
• <code>/markspam</code> - 标记广告并训练
• <code>/listspam</code> - 广告记录列表
• <code>/listbanuser</code> - 封禁列表
• <code>/feedspam</code> - 投喂广告样本
• <code>/markham</code> - 标为正常（纠正误杀）
• <code>/grouphelp</code> - 完整说明

<b>━━━ 🚫 贝叶斯广告拦截 ━━━</b>
• 自动识别广告并删消息；累计 3 次封禁（可配置）
• 详见 <code>/grouphelp</code>
"""


@router.callback_query(F.data == "feature_list")
async def process_callback_feature_list(callback_query: CallbackQuery, state: FSMContext):
    """显示功能列表"""
    user_id = callback_query.from_user.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    await callback_query.message.edit_text(
        text=FEATURE_LIST_TEXT,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback_query.answer()


# 管理命令文本
ADMIN_COMMANDS_TEXT = """
<b>🛡️ 群组管理命令</b>

<b>━━━ 👤 用户管理 ━━━</b>

<code>/ban</code>
封禁用户（回复消息使用）
用户将被踢出并无法再加入群组

<code>/unban</code>
解封用户（回复消息使用）
恢复用户加入群组的权限

<code>/kick</code>
踢出用户（回复消息使用）
踢出后用户仍可重新加入群组

<code>/warn</code>
警告用户（回复消息使用）
累计警告达到上限将自动封禁

<code>/mute [小时]</code>
禁言用户（回复消息使用）
示例：<code>/mute 24</code> 禁言24小时

<b>━━━ 🙈 忽略用户 ━━━</b>

<code>/ignore</code>
忽略用户（回复消息使用）
机器人将不再回复该用户的任何消息

<code>/unignore</code>
取消忽略（回复消息使用）
恢复正常回复该用户

<code>/ignorelist</code>
查看被忽略的用户列表

<b>━━━ 💬 消息管理 ━━━</b>

<code>/del</code>
删除消息（回复消息使用）

<code>/stats [天数]</code>
查看违规统计
示例：<code>/stats 7</code> 查看最近7天

<b>━━━ 🧠 贝叶斯广告（BSS 同款）━━━</b>

<code>/markspam</code>
回复垃圾消息：删除、封禁、训练模型

<code>/listspam</code>
查看广告记录；误杀 <code>/markham 编号</code>

<code>/listbanuser</code>
封禁列表；解封请 <code>/unban</code>

<code>/feedspam 文本</code>
投喂广告样本

<code>/grouphelp</code>
完整群管说明

<i>💡 提示：/markspam /listspam /listbanuser 等需群组管理员；/feedspam 人人可用</i>
"""


@router.callback_query(F.data == "admin_commands")
async def process_callback_admin_commands(callback_query: CallbackQuery, state: FSMContext):
    """显示管理命令列表"""
    user_id = callback_query.from_user.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    await callback_query.message.edit_text(
        text=ADMIN_COMMANDS_TEXT,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback_query.answer()


@router.callback_query(_is_llm_model_select_callback)
async def process_callback_llm_model_set(
    callback_query: CallbackQuery, state: FSMContext
):
    """从 llm_models.yaml 切换模型（Gemini / NVIDIA / OpenRouter）。"""
    if callback_query.from_user.id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    if not await _apply_llm_model_from_callback(callback_query, callback_query.data):
        await callback_query.answer("无效的模型选择")


@router.callback_query(F.data == "pic_setup")
async def process_callback_menu_pic_setup(callback_query: CallbackQuery, state: FSMContext):
    """图片设置"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text=f"{user_data.pic_grade} : {user_data.pic_size} ",
        reply_markup=keyboard_pic,
    )
    await callback_query.answer()


@router.callback_query(F.data == "set_sd")
async def process_callback_set_sd(callback_query: CallbackQuery, state: FSMContext):
    """设置图片质量为 SD"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    user_data = await get_or_create_user_data(user_id, chat_id)

    if user_data.pic_grade == "standard":
        return

    user_data.pic_grade = "standard"
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text=f"{user_data.pic_grade} : {user_data.pic_size} ",
        reply_markup=keyboard_pic,
    )
    await callback_query.answer()


@router.callback_query(F.data == "set_hd")
async def process_callback_set_hd(callback_query: CallbackQuery, state: FSMContext):
    """设置图片质量为 HD"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    user_data = await get_or_create_user_data(user_id, chat_id)

    if user_data.pic_grade == "hd":
        return

    user_data.pic_grade = "hd"
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text=f"{user_data.pic_grade} : {user_data.pic_size} ",
        reply_markup=keyboard_pic,
    )
    await callback_query.answer()


@router.callback_query(F.data == "set_1024x1024")
async def process_callback_set_1024x1024(callback_query: CallbackQuery, state: FSMContext):
    """设置图片尺寸为 1024x1024"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    user_data = await get_or_create_user_data(user_id, chat_id)

    if user_data.pic_size == "1024x1024":
        return

    user_data.pic_size = "1024x1024"
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text=f"{user_data.pic_grade} : {user_data.pic_size} ",
        reply_markup=keyboard_pic,
    )
    await callback_query.answer()


@router.callback_query(F.data == "set_1024x1792")
async def process_callback_set_1024x1792(callback_query: CallbackQuery, state: FSMContext):
    """设置图片尺寸为 1024x1792"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    user_data = await get_or_create_user_data(user_id, chat_id)

    if user_data.pic_size == "1024x1792":
        return

    user_data.pic_size = "1024x1792"
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text=f"{user_data.pic_grade} : {user_data.pic_size} ",
        reply_markup=keyboard_pic,
    )
    await callback_query.answer()


@router.callback_query(F.data == "set_1792x1024")
async def process_callback_set_1792x1024(callback_query: CallbackQuery, state: FSMContext):
    """设置图片尺寸为 1792x1024"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    user_data = await get_or_create_user_data(user_id, chat_id)

    if user_data.pic_size == "1792x1024":
        return

    user_data.pic_size = "1792x1024"
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text=f"{user_data.pic_grade} : {user_data.pic_size} ",
        reply_markup=keyboard_pic,
    )
    await callback_query.answer()


@router.callback_query(F.data == "back_menu")
async def process_callback_menu_back(callback_query: CallbackQuery, state: FSMContext):
    """返回主菜单"""
    user_id = callback_query.from_user.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    await callback_query.message.edit_text(
        text="请选择操作：", reply_markup=keyboard
    )


@router.callback_query(F.data == "context")
async def process_callback_context(callback_query: CallbackQuery, state: FSMContext):
    """显示对话上下文"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)
    history = await generate_history(user_data.messages)

    if not history:
        await callback_query.message.edit_text(text="上下文为空", reply_markup=None)
        await callback_query.answer()
        return

    await send_history(bot, callback_query.from_user.id, history)
    await callback_query.message.edit_text(text="上下文：", reply_markup=None)
    await callback_query.answer()


@router.callback_query(F.data == "clear")
async def process_callback_clear(callback_query: CallbackQuery, state: FSMContext):
    """清除对话上下文"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)

    user_data.messages = []
    user_data.count_messages = 0

    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(text="上下文已清除", reply_markup=None)
    await callback_query.answer()


@router.callback_query(F.data == "voice_answer_add")
async def process_callback_voice_answer_add(callback_query: CallbackQuery, state: FSMContext):
    """启用语音回复"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)
    user_data.voice_answer = True
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text="语音回复已启用", reply_markup=None
    )
    await callback_query.answer()


@router.callback_query(F.data == "voice_answer_del")
async def process_callback_voice_answer_del(callback_query: CallbackQuery, state: FSMContext):
    """禁用语音回复"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)
    user_data.voice_answer = False
    await save_user_data(user_id, chat_id)

    await callback_query.message.edit_text(
        text="语音回复已禁用",
        reply_markup=None,
    )
    await callback_query.answer()


@router.callback_query(F.data == "info")
async def process_callback_info(callback_query: CallbackQuery, state: FSMContext):
    """显示机器人信息"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)
    settings = await get_chat_settings_data(
        user_id, chat_id, callback_query.message.chat.type
    )
    model_label = format_model_display(settings.model, settings.model_message_info)

    info_voice_answer = "已启用" if user_data.voice_answer else "已禁用"
    info_system_message = (
        "未设置" if not settings.system_message else settings.system_message
    )

    info_messages = (
        f"<i>总消息数：</i> <b>{user_data.count_messages}</b>\n"
        f"<i>当前模型：</i> <b>{model_label}</b>\n"
        f"<i>语音回复：</i> <b>{info_voice_answer}</b>\n"
        f"<i>机器人启动时间：</i> <b>{formatted_datetime}</b>\n"
        f"<i>您的用户 ID：</i> <b>{user_id}</b>\n"
        f"<i>系统角色：</i> <b>{info_system_message}</b>\n"
        f"<i>图片质量：</i> <b>{user_data.pic_grade}</b>\n"
        f"<i>图片尺寸：</i> <b>{user_data.pic_size}</b>"
    )

    await callback_query.message.edit_text(
        text=info_messages,
        reply_markup=None,
    )
    await callback_query.answer()


@router.callback_query(F.data == "change_value")
async def process_callback_change_value(callback_query: types.CallbackQuery, state: FSMContext):
    """设置系统角色"""
    user_id = callback_query.from_user.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    await state.set_state(ChangeValueState.waiting_for_new_value)

    await callback_query.message.edit_text(
        text=system_message_text,
        reply_markup=None,
    )
    await callback_query.answer()


@router.callback_query(F.data == "delete_value")
async def process_callback_delete_value(callback_query: CallbackQuery, state: FSMContext):
    """删除系统角色"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    storage_uid, storage_cid = _model_storage_ids(callback_query)
    settings = await get_or_create_user_data(storage_uid, storage_cid)
    settings.system_message = ""
    await save_user_data(storage_uid, storage_cid)

    await callback_query.message.edit_text(
        text="<b>系统角色已删除</b>",
        reply_markup=None,
    )
    await callback_query.answer()


# ==================== 音色选择 ====================

# 音色名称映射
VOICE_NAMES = {
    "xiaoxiao": "晓晓 (活泼可爱)",
    "yunxi": "云希 (成熟稳重)",
    "yunyang": "云扬 (新闻播报)",
    "xiaoyi": "晓伊 (温柔知性)",
    "yunxia": "云霞 (活泼开朗)",
    "yunjian": "云健 (运动解说)",
    "cat": "喵喵 (萌系变声)",
}


@router.callback_query(F.data == "voice_select")
async def process_callback_voice_select(callback_query: CallbackQuery, state: FSMContext):
    """显示音色选择菜单"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    user_data = await get_or_create_user_data(user_id, chat_id)
    current_voice = getattr(user_data, 'voice_type', 'xiaoxiao') or 'xiaoxiao'
    current_name = VOICE_NAMES.get(current_voice, "晓晓")

    await callback_query.message.edit_text(
        text=f"🎙️ <b>选择语音音色</b>\n\n当前音色：<b>{current_name}</b>",
        reply_markup=keyboard_voice,
        parse_mode="HTML"
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("voice_"))
async def process_callback_voice_set(callback_query: CallbackQuery, state: FSMContext):
    """设置音色"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    # 排除 voice_select 和 voice_answer_* 回调
    if callback_query.data in ["voice_select", "voice_answer_add", "voice_answer_del"]:
        return

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    # 解析音色键
    voice_key = callback_query.data.replace("voice_", "")
    
    if voice_key not in VOICE_NAMES:
        await callback_query.answer("无效的音色选择")
        return

    user_data = await get_or_create_user_data(user_id, chat_id)
    user_data.voice_type = voice_key
    await save_user_data(user_id, chat_id)

    voice_name = VOICE_NAMES[voice_key]

    await callback_query.message.edit_text(
        text=f"✅ 音色已设置为：<b>{voice_name}</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback_query.answer()


# ==================== NVIDIA 模型选择 ====================


@router.callback_query(F.data == "nvidia_models")
async def process_callback_nvidia_models(callback_query: CallbackQuery, state: FSMContext):
    """显示 NVIDIA 模型选择菜单"""
    user_id = callback_query.from_user.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    await callback_query.message.edit_text(
        text="🚀 <b>选择 NVIDIA 模型</b>\n\n"
             "这些模型通过 NVIDIA NIM（integrate.api.nvidia.com）调用，支持文本与图片理解。\n\n"
             "<i>💡 默认推荐 Step 3.5 Flash（群聊更快）；需要深度推理可切 GLM/Kimi。</i>",
        reply_markup=keyboard_nvidia,
        parse_mode="HTML"
    )
    await callback_query.answer()


# ==================== OpenRouter 模型选择 ====================


@router.callback_query(F.data == "openrouter_models")
async def process_callback_openrouter_models(callback_query: CallbackQuery, state: FSMContext):
    """显示 OpenRouter 模型选择菜单"""
    user_id = callback_query.from_user.id

    if user_id not in OWNER_ID:
        await callback_query.answer("抱歉，您没有访问此机器人的权限。")
        return

    if state is not None:
        await state.clear()

    await callback_query.message.edit_text(
        text="🌐 <b>选择 OpenRouter 模型</b>\n\n"
             "支持更多外部模型，如 Arcee Trinity。\n",
        reply_markup=get_keyboard_openrouter(),
        parse_mode="HTML"
    )
    await callback_query.answer()


