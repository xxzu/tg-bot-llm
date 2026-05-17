"""FSM 状态定义（避免 handlers 互相 import）。"""
from aiogram.fsm.state import State, StatesGroup


class ChangeValueState(StatesGroup):
  waiting_for_new_value = State()
