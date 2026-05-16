# Handlers module
from aiogram import Router

from handlers.commands import router as commands_router
from handlers.callbacks import router as callbacks_router
from handlers.messages import router as messages_router
from handlers.admin import router as admin_router

# 创建主路由器
router = Router()

# 包含所有子路由器
router.include_router(commands_router)
router.include_router(callbacks_router)
router.include_router(admin_router)
router.include_router(messages_router)  # messages 放最后，因为它是通用处理器
