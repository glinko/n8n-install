from aiogram.fsm.state import State, StatesGroup

class AgentState(StatesGroup):
    waiting_for_message = State()
