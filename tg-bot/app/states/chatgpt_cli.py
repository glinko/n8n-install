from aiogram.fsm.state import State, StatesGroup

class ChatGPTCLIState(StatesGroup):
    waiting_for_session_name = State()
    waiting_for_query = State()
