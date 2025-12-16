from aiogram.fsm.state import State, StatesGroup

class TestChatState(StatesGroup):
    waiting_for_message = State()
