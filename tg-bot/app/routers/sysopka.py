from __future__ import annotations

import textwrap
import uuid
import logging
from typing import Sequence

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select

from ..config import settings
from ..db import get_session
from ..models import SysopkaSession, SysopkaMessage, User
from ..services.flowise_client import FlowiseClientError, run_sysopka_agentflow
from ..states.sysopka import SysopkaState
# Legacy constant for backward compatibility
SYSOPKA_BUTTON_TEXT = "Sysopka"

router = Router(name="sysopka")
logger = logging.getLogger(__name__)

# Sysopka specialty types
SYSOPKA_TYPES = {
    "claudecli": "🤖 Claude CLI",
    "proxmox": "🖥️ ProxMox",
    "homenet": "🏠 HomeNET",
    "chatbot": "💬 ChatBOT",
}

def build_sysopka_menu() -> ReplyKeyboardMarkup:
    """Build submenu for Sysopka specialty selection"""
    keyboard = [
        [KeyboardButton(text=SYSOPKA_TYPES["claudecli"]), KeyboardButton(text=SYSOPKA_TYPES["proxmox"])],
        [KeyboardButton(text=SYSOPKA_TYPES["homenet"]), KeyboardButton(text=SYSOPKA_TYPES["chatbot"])],
        [KeyboardButton(text="◀️ Главное меню")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выбери специализацию Сысопки",
    )

def get_sysopka_type_from_text(text: str) -> str | None:
    """Extract sysopka type from button text"""
    for key, value in SYSOPKA_TYPES.items():
        if value.lower() == text.lower():
            return key
    return None

async def _get_active_session(user: User, sysopka_type: str | None = None) -> SysopkaSession | None:
    async with get_session() as session:
        query = select(SysopkaSession).where(
            SysopkaSession.user_id == user.id,
            SysopkaSession.is_active.is_(True),
        )
        if sysopka_type:
            query = query.where(SysopkaSession.sysopka_type == sysopka_type)
        query = query.limit(1)

        result = await session.execute(query)
        return result.scalar_one_or_none()

async def _get_or_create_session(user: User, sysopka_type: str) -> SysopkaSession:
    existing = await _get_active_session(user, sysopka_type)
    if existing:
        return existing

    async with get_session() as session:
        new_session = SysopkaSession(
            user_id=user.id,
            sysopka_type=sysopka_type,
            flowise_session_id=f"sysopka-{sysopka_type}-{user.telegram_id}-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)
        return new_session

async def _deactivate_session(session_id: int) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(SysopkaSession).where(SysopkaSession.id == session_id)
        )
        obj = result.scalar_one_or_none()
        if obj and obj.is_active:
            obj.is_active = False
            session.add(obj)
            await session.commit()

async def _fetch_recent_messages(session_id: int, limit: int = 4) -> Sequence[SysopkaMessage]:
    async with get_session() as session:
        result = await session.execute(
            select(SysopkaMessage)
            .where(SysopkaMessage.session_id == session_id)
            .order_by(SysopkaMessage.created_at.desc())
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
        msg = SysopkaMessage(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            raw_response=raw,
        )
        session.add(msg)
        await session.commit()

# Old handler removed - Sysopka menu is now handled dynamically through start.py
# The submenu items (ClaudeCLI, ProxMox, HomeNET) are handled via _start_sysopka_chat()

async def _start_sysopka_chat(
    message: Message, state: FSMContext, db_user: User, sysopka_type: str, agentflow_id: str
) -> None:
    """Start Sysopka chat session with specified agentflow_id."""
    # Start chat with selected specialty
    session = await _get_or_create_session(db_user, sysopka_type)
    await state.set_state(SysopkaState.waiting_for_message)
    await state.update_data(sysopka_type=sysopka_type, agentflow_id=agentflow_id)

    recent = await _fetch_recent_messages(session.id)
    history_block = ""
    if recent:
        lines = ["Последние сообщения:"]
        for item in recent:
            prefix = "👤" if item.role == "user" else "🔧"
            snippet = item.content.strip()
            snippet = textwrap.shorten(snippet, width=120, placeholder="…")
            lines.append(f"{prefix} {snippet}")
        history_block = "\n".join(lines)

    specialty_name = SYSOPKA_TYPES.get(sysopka_type, sysopka_type)
    intro = (
        f"Привет! Я Сысопка ({specialty_name}) 🔧\n"
        f"Специализация: {specialty_name}\n"
        "Задавай вопросы. Введи /exit чтобы выйти."
    )
    text = intro if not history_block else f"{intro}\n\n{history_block}"
    await message.answer(text)

@router.message(SysopkaState.choosing_specialty)
async def select_sysopka_specialty(message: Message, state: FSMContext, db_user: User):
    """Handle specialty selection"""
    sysopka_type = get_sysopka_type_from_text(message.text)
    
    if not sysopka_type:
        await message.answer("Пожалуйста, выбери специализацию из меню.")
        return

    # Check if this specialty is configured
    agentflow_id = settings.get_sysopka_id(sysopka_type)
    if not agentflow_id:
        await message.answer(
            f"Специализация {SYSOPKA_TYPES[sysopka_type]} еще не настроена.\n"
            "Выбери другую или вернись в главное меню."
        )
        return

    await _start_sysopka_chat(message, state, db_user, sysopka_type, agentflow_id)

@router.message(SysopkaState.waiting_for_message, F.text.casefold() == "/exit")
async def exit_sysopka(message: Message, state: FSMContext, db_user: User):
    user_data = await state.get_data()
    sysopka_type = user_data.get("sysopka_type")
    
    session = await _get_active_session(db_user, sysopka_type)
    if session:
        await _deactivate_session(session.id)
    await state.clear()
    await message.answer("Сысопка прощается 👋 Нажми кнопку снова, чтобы вернуться.")

@router.message(SysopkaState.waiting_for_message, F.text == "/start")
async def exit_to_main_menu(message: Message, state: FSMContext, db_user: User):
    user_data = await state.get_data()
    sysopka_type = user_data.get("sysopka_type")
    
    session = await _get_active_session(db_user, sysopka_type)
    if session:
        await _deactivate_session(session.id)
    await state.clear()

    from .start import _show_main_menu
    await _show_main_menu(message, db_user, state)

@router.message(SysopkaState.waiting_for_message)
async def handle_sysopka_message(message: Message, state: FSMContext, db_user: User):
    user_data = await state.get_data()
    sysopka_type = user_data.get("sysopka_type")
    agentflow_id = user_data.get("agentflow_id")
    
    if not sysopka_type:
        await message.answer("Ошибка: специализация не выбрана. Нажми /exit")
        return

    if not agentflow_id:
        # Fallback to settings if not in state
        agentflow_id = settings.get_sysopka_id(sysopka_type)
        if not agentflow_id:
            await message.answer("Ошибка: agentflow не настроен. Нажми /exit")
            return

    logger.info(f"Received message in Sysopka ({sysopka_type}) from user {db_user.telegram_id}: {message.text[:50] if message.text else 'No text'}")

    if not message.text:
        await message.answer("Отправь текстовое сообщение.")
        return

    session = await _get_or_create_session(db_user, sysopka_type)
    user_text = message.text.strip()
    await _save_message(session.id, db_user.id, "user", user_text)

    logger.info(f"Sending request to Sysopka {sysopka_type} agentflow {agentflow_id} with session_id={session.flowise_session_id}")

    try:
        from ..services.flowise_client import run_agentflow
        flowise_response = await run_agentflow(
            user_text, agentflow_id, session.flowise_session_id
        )
        logger.info(f"Received response from Sysopka {sysopka_type}: {flowise_response.message[:100]}")
    except FlowiseClientError as exc:
        logger.error(f"Sysopka {sysopka_type} agentflow error: {exc}")
        specialty_name = SYSOPKA_TYPES.get(sysopka_type, sysopka_type)
        await message.answer(
            f"Не удалось получить ответ от Сысопки ({specialty_name}). Попробуй позже или /exit."
        )
        await _save_message(
            session.id,
            db_user.id,
            "system",
            f"Sysopka error: {exc}",
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
