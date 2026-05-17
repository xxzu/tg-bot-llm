"""
按钮配置模块
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config.nvidia_models import NVIDIA_MODEL_BUTTONS

BUTTONS_ALL = [
    ("📋 功能列表", "feature_list"),
    ("🛡️ 管理命令", "admin_commands"),
    ("Gemini 3 Pro", "gemini_3_pro"),
    ("Gemini 2.0 Flash", "gemini_2_flash"),
    ("Gemini 1.5 Pro", "gemini_1_5_pro"),
    ("🚀 NVIDIA模型", "nvidia_models"),
    ("🌐 OpenRouter模型", "openrouter_models"),
    ("显示对话上下文", "context"),
    ("清除上下文", "clear"),
    ("启用语音回复", "voice_answer_add"),
    ("禁用语音回复", "voice_answer_del"),
    ("🎙️ 选择音色", "voice_select"),
    ("设定系统角色", "change_value"),
    ("移除系统角色", "delete_value"),
    ("信息", "info"),
]

inline_buttons = [
    InlineKeyboardButton(text=text, callback_data=data) for text, data in BUTTONS_ALL
]

keyboard = InlineKeyboardMarkup(inline_keyboard=[[button] for button in inline_buttons])

pic_buttons = [
    ("SD", "set_sd"),
    ("HD", "set_hd"),
    ("1024x1024", "set_1024x1024"),
    ("1024x1792", "set_1024x1792"),
    ("1792x1024", "set_1792x1024"),
    ("返回菜单", "back_menu"),
]

inline_buttons_pic = [
    InlineKeyboardButton(text=text, callback_data=data) for text, data in pic_buttons
]

keyboard_pic = InlineKeyboardMarkup(
    inline_keyboard=[[button] for button in inline_buttons_pic]
)

# 音色选择按钮
voice_buttons = [
    ("👧 晓晓 (活泼可爱)", "voice_xiaoxiao"),
    ("👨 云希 (成熟稳重)", "voice_yunxi"),
    ("👨 云扬 (新闻播报)", "voice_yunyang"),
    ("👩 晓伊 (温柔知性)", "voice_xiaoyi"),
    ("👧 云霞 (活泼开朗)", "voice_yunxia"),
    ("👨 云健 (运动解说)", "voice_yunjian"),
    ("🐱 喵喵 (萌系变声)", "voice_cat"),
    ("返回菜单", "back_menu"),
]

inline_buttons_voice = [
    InlineKeyboardButton(text=text, callback_data=data) for text, data in voice_buttons
]

keyboard_voice = InlineKeyboardMarkup(
    inline_keyboard=[[button] for button in inline_buttons_voice]
)

# NVIDIA 模型选择按钮（与 config/nvidia_models.py 一致）
nvidia_buttons = list(NVIDIA_MODEL_BUTTONS) + [("返回菜单", "back_menu")]

inline_buttons_nvidia = [
    InlineKeyboardButton(text=text, callback_data=data) for text, data in nvidia_buttons
]

keyboard_nvidia = InlineKeyboardMarkup(
    inline_keyboard=[[button] for button in inline_buttons_nvidia]
)

def get_openrouter_buttons() -> list[tuple[str, str]]:
    from services.llm.registry import get_registry

    return [
        (spec.button_label, spec.menu_callback())
        for spec in get_registry().list_menu_models("openrouter")
    ] + [("返回菜单", "back_menu")]


def get_keyboard_openrouter() -> InlineKeyboardMarkup:
    buttons = get_openrouter_buttons()
    inline = [
        InlineKeyboardButton(text=text, callback_data=data) for text, data in buttons
    ]
    return InlineKeyboardMarkup(inline_keyboard=[[btn] for btn in inline])


# 兼容旧引用；启动前请先 sync OpenRouter 免费模型
keyboard_openrouter = get_keyboard_openrouter()
