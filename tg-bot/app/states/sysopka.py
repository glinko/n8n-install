from aiogram.fsm.state import State, StatesGroup

class SysopkaState(StatesGroup):
    choosing_specialty = State()  # Выбор специализации из подменю
    waiting_for_message = State()  # Общение с выбранным агентом
