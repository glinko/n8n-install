from aiogram.fsm.state import State, StatesGroup

class CursorCLIState(StatesGroup):
    waiting_for_session_name = State()  # Ожидание названия новой сессии
    waiting_for_query = State()  # Ожидание запроса для сессии (session_name сохранен в state)
    adding_flags = State()  # Режим добавления флагов к запросу
