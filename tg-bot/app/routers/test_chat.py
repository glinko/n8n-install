from __future__ import annotations

import textwrap
import uuid
from typing import Sequence

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from ..config import settings
from ..db import get_session
from ..models import TestChatSession, TestChatMessage, User
from ..services.flowise_client import FlowiseClientError, run_testchat_flow
from ..states.test_chat import TestChatState
# Legacy constant for backward compatibility
CHATGPT_BUTTON_TEXT = "ChatGPT"

router = Router(name="test_chat")

async def _get_active_session(user: User) -> TestChatSession | None:
    async with get_session() as session:
        result = await session.execute(
            select(TestChatSession)
            .where(
                TestChatSession.user_id == user.id,
                TestChatSession.is_active.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

async def _get_or_create_session(user: User) -> TestChatSession:
    existing = await _get_active_session(user)
    if existing:
        return existing

    async with get_session() as session:
        new_session = TestChatSession(
            user_id=user.id,
            flowise_session_id=f"testchat-{user.telegram_id}-{uuid.uuid4().hex}",
            is_active=True,
        )
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)
        return new_session

async def _deactivate_session(session_id: int) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(TestChatSession).where(TestChatSession.id == session_id)
        )
        obj = result.scalar_one_or_none()
        if obj and obj.is_active:
            obj.is_active = False
            session.add(obj)
            await session.commit()

async def _fetch_recent_messages(session_id: int, limit: int = 4) -> Sequence[TestChatMessage]:
    async with get_session() as session:
        result = await session.execute(
            select(TestChatMessage)
            .where(TestChatMessage.session_id == session_id)
            .order_by(TestChatMessage.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

async def _save_message(
    session_id: int,
    user_id: int,
    role: str,
    content: str,
    raw: dict | None = None,
) -> None:
    async with get_session() as session:
        msg = TestChatMessage(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            raw_response=raw,
        )
        session.add(msg)
        await session.commit()

async def _start_test_chat(
    message: Message, state: FSMContext, db_user: User, agentflow_id: str | None = None
) -> None:
    """Start test chat session. agentflow_id can be provided or will use default from settings."""
    session = await _get_or_create_session(db_user)
    await state.set_state(TestChatState.waiting_for_message)
    
    # Store agentflow_id in state if provided
    if agentflow_id:
        await state.update_data(agentflow_id=agentflow_id)

    recent = await _fetch_recent_messages(session.id)
    history_block = ""
    if recent:
        lines = ["Последние сообщения:"]
        for item in recent:
            prefix = "👤" if item.role == "user" else "🤖"
            snippet = item.content.strip()
            snippet = textwrap.shorten(snippet, width=120, placeholder="…")
            lines.append(f"{prefix} {snippet}")
        history_block = "\n".join(lines)

    intro = (
        "Вы в режиме ChatGPT. Отправьте текстовое сообщение, и я отвечу.\n"
        "Введите /exit чтобы выйти из режима."
    )
    text = intro if not history_block else f"{intro}\n\n{history_block}"
    await message.answer(text)

@router.callback_query(F.data == "menu:TEST_CHAT")
async def enter_test_chat(callback: CallbackQuery, state: FSMContext, db_user: User):
    if not settings.has_flowise_testchat:
        missing = []
        if not settings.flowise_api_key:
            missing.append("FLOWISE_API_KEY")
        if not settings.testchat_chatflow_id:
            missing.append("TESTCHAT_CHATFLOW_ID")
        message = "Flowise не настроен."
        if missing:
            message += " Отсутствуют: " + ", ".join(missing)
        await callback.answer(message, show_alert=True)
        return

    await _start_test_chat(callback.message, state, db_user)
    await callback.answer()

# Legacy handler removed - ChatGPT is now handled dynamically through start.py
# The button is processed via action_type="flowise_agentflow" in the menu

@router.message(TestChatState.waiting_for_message, F.text.casefold() == "/exit")
async def exit_test_chat(message: Message, state: FSMContext, db_user: User):
    session = await _get_active_session(db_user)
    if session:
        await _deactivate_session(session.id)
    await state.clear()
    await message.answer("Режим TestChat завершён. Нажмите кнопку снова, чтобы вернуться.")

@router.message(TestChatState.waiting_for_message, F.text == "/start")
async def exit_to_main_menu(message: Message, state: FSMContext, db_user: User):
    session = await _get_active_session(db_user)
    if session:
        await _deactivate_session(session.id)
    await state.clear()

    from .start import _show_main_menu
    await _show_main_menu(message, db_user, state)

@router.message(TestChatState.waiting_for_message)
async def handle_test_chat_message(message: Message, state: FSMContext, db_user: User):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Received message in TestChat state from user {db_user.telegram_id}: {message.text[:50] if message.text else 'No text'}")

    if not message.text:
        await message.answer("Отправьте текстовое сообщение.")
        return

    session = await _get_or_create_session(db_user)
    user_text = message.text.strip()
    await _save_message(session.id, db_user.id, "user", user_text)

    # Get agentflow_id from state or use default from settings
    user_data = await state.get_data()
    agentflow_id = user_data.get("agentflow_id") or settings.testchat_chatflow_id
    
    if not agentflow_id:
        await message.answer("Ошибка: agentflow не настроен. Попробуйте позже или /exit.")
        return

    logger.info(f"Sending request to Flowise agentflow {agentflow_id} with session_id={session.flowise_session_id}")

    try:
        from ..services.flowise_client import run_agentflow
        flowise_response = await run_agentflow(
            user_text, agentflow_id, session.flowise_session_id
        )
        logger.info(f"Received response from Flowise: {flowise_response.message[:100]}")
    except FlowiseClientError as exc:
        logger.error(f"Flowise error: {exc}")
        await message.answer(
            "Не удалось получить ответ от Flowise. Попробуйте позже или /exit."
        )
        await _save_message(
            session.id,
            db_user.id,
            "system",
            f"Flowise error: {exc}",
        )
        return

    await _save_message(
        session.id,
        db_user.id,
        "assistant",
        flowise_response.message,
        raw=flowise_response.raw,
    )
    await message.answer(flowise_response.message)
