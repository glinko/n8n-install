# app/routers/agent.py
from __future__ import annotations

import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..models import User
from ..states.agent import AgentState

router = Router(name="agent")
logger = logging.getLogger(__name__)

@router.message(AgentState.waiting_for_message, F.text.casefold() == "/exit")
async def exit_agent(message: Message, state: FSMContext, db_user: User):
    """Exit Agent mode."""
    await state.clear()
    await message.answer("Режим Agent завершён. Используйте /start для возврата в меню.")
    from .start import _show_main_menu
    await _show_main_menu(message, db_user, state)

@router.message(AgentState.waiting_for_message, F.text == "/start")
async def exit_to_main_menu(message: Message, state: FSMContext, db_user: User):
    """Return to main menu."""
    await state.clear()
    from .start import _show_main_menu
    await _show_main_menu(message, db_user, state)

@router.message(AgentState.waiting_for_message)
async def handle_agent_query(message: Message, state: FSMContext, db_user: User):
    """Handle Agent query."""
    query = message.text.strip()
    
    if not query:
        await message.answer("Пожалуйста, введите запрос.")
        return
    
    # Заглушка: пока просто отвечаем, что функционал в разработке
    await message.answer(
        "🤖 Agent (в разработке)\n\n"
        f"Ваш запрос: {query}\n\n"
        "Этот функционал будет подключен к n8n или Flowise.\n"
        "Введите следующий запрос или /exit для выхода."
    )

async def start_agent(message: Message, state: FSMContext, db_user: User):
    """Start Agent mode."""
    await state.set_state(AgentState.waiting_for_message)
    await message.answer(
        "🤖 **Agent**\n\n"
        "Вы в режиме Agent. Этот AI-агент будет подключен к n8n или Flowise.\n"
        "Введите /exit чтобы выйти из режима."
    )
