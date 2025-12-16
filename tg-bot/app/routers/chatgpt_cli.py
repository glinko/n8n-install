from __future__ import annotations

import logging
import asyncio
import shlex
import re
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select, and_
import docker

from ..db import get_session
from ..models import User, ChatGPTCLISession, ChatGPTCLIMessage, MenuItem
from ..states.chatgpt_cli import ChatGPTCLIState

router = Router(name="chatgpt_cli")
logger = logging.getLogger(__name__)

NEW_SESSION_BUTTON = "New Session"
BACK_TO_MAIN = "◀️ Главное меню"

def escape_markdown(text: str) -> str:
    """Escape special Markdown characters for Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def build_chatgpt_cli_menu(sessions: list[ChatGPTCLISession]) -> ReplyKeyboardMarkup:
    """Build ChatGPT CLI submenu with sessions."""
    keyboard_rows: list[list[KeyboardButton]] = []
    
    # First row: New Session button
    keyboard_rows.append([
        KeyboardButton(text=NEW_SESSION_BUTTON)
    ])
    
    # Session buttons (up to 2 per row)
    i = 0
    while i < len(sessions):
        row = []
        for _ in range(min(2, len(sessions) - i)):
            session = sessions[i]
            row.append(KeyboardButton(text=session.session_name))
            i += 1
        if row:
            keyboard_rows.append(row)
    
    # Back button
    keyboard_rows.append([KeyboardButton(text=BACK_TO_MAIN)])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )

async def get_user_sessions(user_id: int) -> list[ChatGPTCLISession]:
    """Get all ChatGPT CLI sessions for user."""
    async with get_session() as session:
        result = await session.execute(
            select(ChatGPTCLISession)
            .where(ChatGPTCLISession.user_id == user_id)
            .order_by(ChatGPTCLISession.created_at.desc())
        )
        return list(result.scalars().all())

async def create_session(user_id: int, session_name: str) -> tuple[ChatGPTCLISession, str | None]:
    """
    Create new ChatGPT CLI session in database.
    Returns (session, error_message).
    """
    try:
        # Check if session already exists
        async with get_session() as db_session:
            existing = await db_session.execute(
                select(ChatGPTCLISession).where(
                    and_(
                        ChatGPTCLISession.user_id == user_id,
                        ChatGPTCLISession.session_name == session_name
                    )
                )
            )
            if existing.scalar_one_or_none():
                return (None, f"Сессия '{session_name}' уже существует")
        
        # Create session record
        async with get_session() as db_session:
            new_session = ChatGPTCLISession(
                user_id=user_id,
                session_name=session_name
            )
            db_session.add(new_session)
            await db_session.commit()
            await db_session.refresh(new_session)
            logger.info(f"Created ChatGPT CLI session '{session_name}' for user {user_id}")
            return (new_session, None)
            
    except Exception as e:
        logger.error(f"Error creating ChatGPT CLI session: {e}", exc_info=True)
        return (None, f"Ошибка создания сессии: {str(e)}")

async def get_or_create_session(user_id: int, session_name: str) -> ChatGPTCLISession | None:
    """Get session or create if doesn't exist."""
    async with get_session() as db_session:
        result = await db_session.execute(
            select(ChatGPTCLISession).where(
                and_(
                    ChatGPTCLISession.user_id == user_id,
                    ChatGPTCLISession.session_name == session_name
                )
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session
    # Create if doesn't exist
    new_session, error = await create_session(user_id, session_name)
    return new_session

async def save_message(session_id: int, user_id: int, query: str, response: str | None, model_used: str | None = None):
    """Save message to database."""
    async with get_session() as db_session:
        message = ChatGPTCLIMessage(
            session_id=session_id,
            user_id=user_id,
            query=query,
            response=response,
            model_used=model_used
        )
        db_session.add(message)
        await db_session.commit()

async def execute_chatgpt_command(query: str, model_override: str | None = None) -> tuple[str, bool, str | None]:
    """
    Execute ChatGPT CLI command via docker exec.
    Returns (output, success, model_used).
    """
    try:
        client = docker.from_env()
        query_escaped = query.replace("'", "'\\''")
        
        # Build command
        if model_override:
            base_cmd = f"chatgpt --model {shlex.quote(model_override)} '{query_escaped}'"
        else:
            base_cmd = f"chatgpt '{query_escaped}'"
        
        logger.info(f"Executing ChatGPT CLI command: docker exec chatgpt-cli {base_cmd}")
        
        loop = asyncio.get_event_loop()
        container = await loop.run_in_executor(None, lambda: client.containers.get('chatgpt-cli'))
        
        # Get environment variables from container
        container_env = container.attrs['Config']['Env'] or []
        env_dict = {}
        for env_var in container_env:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                env_dict[key] = value
        
        exec_result = await loop.run_in_executor(
            None,
            lambda: container.exec_run(
                ['sh', '-c', base_cmd],
                stdout=True,
                stderr=True,
                user='chatgpt',
                environment=env_dict
            )
        )
        
        output = exec_result.output.decode('utf-8', errors='replace')
        logger.info(f"Command exit code: {exec_result.exit_code}, output length: {len(output)}")
        
        # Extract model name from output if present
        model_used = None
        lines = output.split('\n')
        for line in lines:
            if 'Detected latest GPT model:' in line or 'Using model from' in line:
                model_used = line.split(':')[-1].strip() if ':' in line else None
                break
        
        if exec_result.exit_code == 0:
            # Remove the model detection line if present
            filtered_lines = [line for line in lines if not line.startswith('Detected latest GPT model:') and not line.startswith('Using model from')]
            output = '\n'.join(filtered_lines).strip()
            return (output, True, model_used)
        else:
            error_msg = output if output else "Команда завершилась с ошибкой без вывода"
            logger.error(f"Command failed with exit code {exec_result.exit_code}: {error_msg[:200]}")
            return (f"Ошибка выполнения команды (код {exec_result.exit_code}):\n{error_msg[:1000]}", False, model_used)
            
    except docker.errors.NotFound:
        logger.error("Container 'chatgpt-cli' not found")
        return ("Ошибка: контейнер 'chatgpt-cli' не найден", False, None)
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        return (f"Ошибка Docker API: {str(e)}", False, None)
    except Exception as e:
        logger.error(f"Error executing ChatGPT CLI command: {e}", exc_info=True)
        return (f"Ошибка выполнения команды: {str(e)}", False, None)

async def show_chatgpt_cli_menu(message: Message, db_user: User, update_existing: bool = False):
    """Show ChatGPT CLI submenu with sessions."""
    sessions = await get_user_sessions(db_user.id)
    keyboard = build_chatgpt_cli_menu(sessions)
    
    text = "**ChatGPT CLI**\n\nВыберите сессию или создайте новую:"
    if update_existing:
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

async def handle_chatgpt_cli_button(message: Message, state: FSMContext, db_user: User):
    """Handle button press in ChatGPT CLI submenu."""
    text = message.text.strip()
    logger.info(f"handle_chatgpt_cli_button: text='{text}', user_id={db_user.id}")
    
    current_state = await state.get_state()
    
    if text == NEW_SESSION_BUTTON:
        logger.info("New Session button pressed")
        await state.set_state(ChatGPTCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
    elif text.casefold() == "/delete":
        # Handle /delete command even from submenu
        if current_state and str(current_state).startswith("ChatGPTCLIState"):
            await delete_current_session(message, state, db_user)
        else:
            await message.answer("Команда /delete доступна только в активной сессии ChatGPT CLI.")
    else:
        # Check if it's a session name
        sessions = await get_user_sessions(db_user.id)
        session_names = [s.session_name for s in sessions]
        if text in session_names:
            await handle_session_button(message, state, db_user, text)
        else:
            # If we're in waiting_for_query state, let the state handler process it
            if current_state == ChatGPTCLIState.waiting_for_query:
                # Don't handle here, let handle_query_input process it
                return
            await message.answer("Неизвестная команда. Используйте кнопки меню.")

async def handle_session_button(message: Message, state: FSMContext, db_user: User, session_name: str):
    """Handle session name button press."""
    db_session = await get_or_create_session(db_user.id, session_name)
    
    if not db_session:
        await message.answer("Сессия не найдена. Выберите сессию из меню.")
        await show_chatgpt_cli_menu(message, db_user)
        return
    
    await state.update_data(session_name=session_name)
    await state.set_state(ChatGPTCLIState.waiting_for_query)
    
    await message.answer(f"Введите запрос для сессии **{session_name}**:", parse_mode="Markdown")

@router.message(ChatGPTCLIState.waiting_for_session_name)
async def handle_session_name_input(message: Message, state: FSMContext, db_user: User):
    """Handle session name input for new session."""
    logger.info(f"handle_session_name_input: received '{message.text}' from user {db_user.id}")
    session_name = message.text.strip()
    
    # Validate session name (English, no spaces)
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_name):
        await message.answer("Название сессии должно содержать только английские буквы, цифры, дефисы и подчеркивания. Попробуйте снова:")
        return
    
    # Check if session already exists for this user
    async with get_session() as db_session:
        result = await db_session.execute(
            select(ChatGPTCLISession).where(
                and_(
                    ChatGPTCLISession.user_id == db_user.id,
                    ChatGPTCLISession.session_name == session_name
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            await message.answer(f"Сессия '{session_name}' уже существует. Выберите её из меню или введите другое название:")
            return
    
    # Create session
    logger.info(f"Creating new session '{session_name}' for user {db_user.id}")
    await message.answer("Создаю сессию...")
    
    new_session, error = await create_session(db_user.id, session_name)
    
    if error:
        await message.answer(f"❌ {error}")
        return
    
    if not new_session:
        await message.answer("❌ Ошибка: не удалось создать сессию")
        return
    
    await state.update_data(session_name=session_name)
    await state.set_state(ChatGPTCLIState.waiting_for_query)
    
    await message.answer(
        f"✅ Сессия '{session_name}' создана.\n\n"
        f"Введите запрос для сессии {session_name}:"
    )

@router.message(ChatGPTCLIState.waiting_for_query, F.text.casefold() == "/exit")
async def exit_chatgpt_cli(message: Message, state: FSMContext, db_user: User):
    """Exit ChatGPT CLI mode."""
    await state.clear()
    await message.answer("Режим ChatGPT CLI завершён. Используйте /start для возврата в меню.")
    from .start import _show_main_menu
    await _show_main_menu(message, db_user, state)

@router.message(ChatGPTCLIState.waiting_for_query, F.text == "/start")
async def exit_to_main_menu(message: Message, state: FSMContext, db_user: User):
    """Return to main menu."""
    await state.clear()
    from .start import _show_main_menu
    await _show_main_menu(message, db_user, state)

@router.message(ChatGPTCLIState.waiting_for_query)
async def handle_query_input(message: Message, state: FSMContext, db_user: User):
    """Handle ChatGPT CLI query input."""
    query_text = message.text.strip()
    
    if not query_text:
        await message.answer("Пожалуйста, введите запрос.")
        return
    
    # Get session name from state
    user_data = await state.get_data()
    session_name = user_data.get("session_name")
    
    if not session_name:
        await message.answer("Ошибка: сессия не определена. Выберите сессию заново.")
        await state.clear()
        await show_chatgpt_cli_menu(message, db_user)
        return
    
    # Get or create session
    db_session = await get_or_create_session(db_user.id, session_name)
    if not db_session:
        await message.answer("Ошибка: сессия не найдена. Создайте сессию заново.")
        await state.clear()
        await show_chatgpt_cli_menu(message, db_user)
        return
    
    # Show typing indicator
    await message.answer("⏳ Обрабатываю запрос...")
    
    # Execute command
    output, success, model_used = await execute_chatgpt_command(query_text)
    
    # Save message to database
    await save_message(db_session.id, db_user.id, query_text, output if success else None, model_used)
    
    if success:
        # Truncate long output
        if len(output) > 4000:
            output = output[:4000] + "\n\n... (вывод обрезан, слишком длинный)"
        
        # Try to send with Markdown, fallback to plain text on error
        try:
            escaped_output = escape_markdown(output)
            await message.answer(f"**Сессия {session_name}:**\n\n{escaped_output}", parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to send with Markdown, falling back to plain text: {e}")
            await message.answer(f"Сессия {session_name}:\n\n{output}")
    else:
        await message.answer(output)
    
    # Ask for next query
    await message.answer(f"Введите следующий запрос для сессии {session_name} или /exit для выхода:")

async def delete_current_session(message: Message, state: FSMContext, db_user: User):
    """Delete current ChatGPT CLI session."""
    user_data = await state.get_data()
    session_name = user_data.get("session_name")
    
    if not session_name:
        await message.answer("Ошибка: текущая сессия не определена.")
        return
    
    async with get_session() as db_session:
        result = await db_session.execute(
            select(ChatGPTCLISession).where(
                and_(
                    ChatGPTCLISession.user_id == db_user.id,
                    ChatGPTCLISession.session_name == session_name
                )
            )
        )
        session_to_delete = result.scalar_one_or_none()
        
        if not session_to_delete:
            await message.answer(f"Сессия '{session_name}' не найдена.")
            await state.clear()
            await show_chatgpt_cli_menu(message, db_user)
            return
        
        # Check if there are messages for this session
        messages_result = await db_session.execute(
            select(ChatGPTCLIMessage).where(
                ChatGPTCLIMessage.session_id == session_to_delete.id
            )
        )
        messages_count = len(list(messages_result.scalars().all()))
        session_id_to_delete = session_to_delete.id
        
        # Delete the session
        try:
            await db_session.delete(session_to_delete)
            await db_session.commit()
            logger.info(f"Deleted ChatGPTCLI session '{session_name}' (id={session_id_to_delete}) for user {db_user.id}. Preserved {messages_count} messages with session_id set to NULL.")
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting session '{session_name}': {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при удалении сессии: {str(e)}")
            return
    
    # Get ChatGPT CLI menu item ID to restore parent_id after clearing state
    async with get_session() as db_session:
        result = await db_session.execute(
            select(MenuItem).where(MenuItem.key == "SYSOPKA_CHATGPT")
        )
        chatgpt_cli_menu_item = result.scalar_one_or_none()
        if chatgpt_cli_menu_item:
            await state.update_data(menu_parent_id=chatgpt_cli_menu_item.id)
    
    await state.clear()
    await show_chatgpt_cli_menu(message, db_user)
    await message.answer(f"✅ Сессия '{session_name}' удалена. История сообщений ({messages_count} сообщений) сохранена.")
