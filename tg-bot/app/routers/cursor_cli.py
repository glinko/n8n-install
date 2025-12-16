from __future__ import annotations

import re
import logging
import asyncio
import shlex
import json
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select, and_, delete
from typing import Sequence
import docker

from ..db import get_session
from ..models import User, CursorCLISession, CursorCLIMessage, MenuItem
from ..states.cursor_cli import CursorCLIState
from ..menu import build_menu_keyboard
from ..services.host_executor import execute_host_command_simple, ALLOWED_HOST_COMMANDS

router = Router(name="cursor_cli")
logger = logging.getLogger(__name__)

NEW_SESSION_BUTTON = "New Session"
FLAGS_BUTTON = "Flags"
BACK_TO_MAIN = "◀️ Главное меню"

# Note: BACK_TO_MAIN button is handled in start.py, not here
# to avoid conflicts with main menu handling

def build_cursor_cli_menu(sessions: list[CursorCLISession]) -> ReplyKeyboardMarkup:
    """Build CursorCLI submenu with sessions."""
    keyboard_rows: list[list[KeyboardButton]] = []
    
    # First row: New Session and Flags
    keyboard_rows.append([
        KeyboardButton(text=NEW_SESSION_BUTTON),
        KeyboardButton(text=FLAGS_BUTTON)
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

async def get_user_sessions(user_id: int) -> list[CursorCLISession]:
    """Get all CursorCLI sessions for user."""
    async with get_session() as session:
        result = await session.execute(
            select(CursorCLISession)
            .where(CursorCLISession.user_id == user_id)
            .order_by(CursorCLISession.created_at.desc())
        )
        return list(result.scalars().all())

async def create_session_with_uuid(user_id: int, session_name: str) -> tuple[CursorCLISession, str | None]:
    """
    Create new Cursor CLI session in database.
    Cursor CLI creates sessions automatically on first query, so we create DB record
    without UUID initially. UUID (chat_id) will be obtained from first query response.
    Returns (session, error_message).
    """
    try:
        # Check if session already exists
        async with get_session() as db_session:
            existing = await db_session.execute(
                select(CursorCLISession).where(
                    and_(
                        CursorCLISession.user_id == user_id,
                        CursorCLISession.session_name == session_name
                    )
                )
            )
            if existing.scalar_one_or_none():
                return (None, f"Сессия '{session_name}' уже существует")
        
        # Create session record without UUID - it will be set on first query
        async with get_session() as db_session:
            new_session = CursorCLISession(
                user_id=user_id,
                session_name=session_name,
                uuid=None  # Will be set on first real query
            )
            db_session.add(new_session)
            await db_session.commit()
            await db_session.refresh(new_session)
            logger.info(f"Created session '{session_name}' without UUID (will be set on first query)")
            return (new_session, None)
            
    except Exception as e:
        logger.error(f"Error creating Cursor CLI session: {e}", exc_info=True)
        return (None, f"Ошибка создания сессии: {str(e)}")

async def get_or_create_session(user_id: int, session_name: str) -> CursorCLISession:
    """Get existing session or return None (sessions must be created via create_session_with_uuid)."""
    async with get_session() as session:
        result = await session.execute(
            select(CursorCLISession).where(
                and_(
                    CursorCLISession.user_id == user_id,
                    CursorCLISession.session_name == session_name
                )
            )
        )
        existing = result.scalar_one_or_none()
        return existing

async def save_message(session_id: int, user_id: int, query: str, response: str | None = None, flags_used: str | None = None):
    """Save CursorCLI message to database."""
    async with get_session() as session:
        msg = CursorCLIMessage(
            session_id=session_id,
            user_id=user_id,
            query=query,
            response=response,
            flags_used=flags_used
        )
        session.add(msg)
        await session.commit()

async def execute_cursor_command(session_uuid: str | None, query: str, flags: str | None = None) -> tuple[str, bool, str | None]:
    """
    Execute docker exec command for Cursor CLI.
    Returns (output, success, chat_id).
    
    Command format: 
    - If session_uuid (chat_id) exists: cursor-agent -p "QUERY" --resume CHAT_ID [FLAGS]
    - If no session_uuid: cursor-agent -p "QUERY" [FLAGS] (creates new session)
    """
    try:
        # Connect to Docker daemon (uses DOCKER_HOST env or /var/run/docker.sock)
        client = docker.from_env()
        
        # Build command with -p (print) flag for non-interactive mode
        # Escape single quotes in query for shell
        query_escaped = query.replace("'", "'\\''")
        
        # Build command string with explicit API key and output format
        # Use text format by default for better compatibility
        if session_uuid:
            # Resume existing session
            base_cmd = f"cursor-agent --api-key \"$CURSOR_API_KEY\" -p --output-format text '{query_escaped}' --resume {shlex.quote(session_uuid)}"
        else:
            # Create new session (first query)
            base_cmd = f"cursor-agent --api-key \"$CURSOR_API_KEY\" -p --output-format text '{query_escaped}'"
        
        # Add flags if provided
        if flags and flags.strip():
            flags_clean = flags.strip()
            base_cmd = f"{base_cmd} {flags_clean}"
        
        logger.info(f"Executing Cursor CLI command: docker exec cursor-code-console {base_cmd}")
        
        loop = asyncio.get_event_loop()
        container = await loop.run_in_executor(None, lambda: client.containers.get('cursor-code-console'))
        
        # Execute with shell command
        # Get environment variables from container
        container_env = container.attrs['Config']['Env'] or []
        env_dict = {}
        for env_var in container_env:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                env_dict[key] = value
        
        logger.info(f"Executing with environment: CURSOR_API_KEY={'set' if 'CURSOR_API_KEY' in env_dict else 'not set'}")
        
        exec_result = await loop.run_in_executor(
            None,
            lambda: container.exec_run(
                ['sh', '-c', base_cmd],
                stdout=True,
                stderr=True,
                user='cursor',
                environment=env_dict
            )
        )
        
        output = exec_result.output.decode('utf-8', errors='replace')
        logger.info(f"Command exit code: {exec_result.exit_code}, output length: {len(output)}")
        
        if exec_result.exit_code == 0:
            if not output or len(output.strip()) == 0:
                logger.warning(f"Command succeeded but output is empty. This may indicate cursor-agent requires additional setup or authentication.")
                # This is a known issue with cursor-agent in headless mode
                return ("⚠️ Cursor-agent выполнен, но ответ пуст.\n\nЭто известная проблема с cursor-agent в headless режиме. Возможные причины:\n• API ключ не настроен корректно\n• Cursor-agent требует интерактивной авторизации\n• Версия cursor-agent имеет проблемы с headless режимом\n\nПопробуйте:\n1. Проверить API ключ в .env файле\n2. Выполнить авторизацию через `cursor-agent login`\n3. Обновить cursor-agent до последней версии", False, None)
            
            # Try to extract chat_id from output if it's a new session
            chat_id = None
            if not session_uuid:
                try:
                    json_start = output.find('{')
                    json_end = output.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = output[json_start:json_end]
                        response_data = json.loads(json_str)
                        chat_id = response_data.get('chat_id') or response_data.get('chatId') or response_data.get('id')
                        logger.info(f"Extracted chat_id from response: {chat_id}")
                except Exception as e:
                    logger.debug(f"Could not extract chat_id from output: {e}")
                    pass
            return (output, True, chat_id)
        else:
            error_msg = output if output else "Команда завершилась с ошибкой без вывода"
            logger.error(f"Command failed with exit code {exec_result.exit_code}: {error_msg[:200]}")
            return (f"Ошибка выполнения команды (код {exec_result.exit_code}):\n{error_msg[:1000]}", False, None)
            
    except docker.errors.NotFound:
        logger.error("Container 'cursor-code-console' not found")
        return ("Ошибка: контейнер 'cursor-code-console' не найден", False, None)
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        return (f"Ошибка Docker API: {str(e)}", False, None)
    except Exception as e:
        logger.error(f"Error executing Cursor CLI command: {e}", exc_info=True)
        return (f"Ошибка выполнения команды: {str(e)}", False, None)

async def end_cursor_session(session_uuid: str | None) -> bool:
    """
    End Cursor CLI session.
    Note: Cursor CLI doesn't have an explicit session stop command.
    Sessions are managed automatically. This function is kept for API consistency.
    Returns True if session_uuid exists (sessions don't need explicit termination).
    """
    if not session_uuid:
        return True
    # Cursor CLI sessions are automatically managed, no explicit termination needed
    logger.info(f"Session {session_uuid} will be managed by Cursor CLI automatically")
    return True

def parse_flags_from_query(query: str) -> tuple[str, str | None]:
    """
    Parse flags from query text.
    Returns (query_without_flags, flags_text).
    """
    # Find #flags marker (case insensitive)
    match = re.search(r'#flags\s*(.*?)$', query, re.IGNORECASE | re.DOTALL)
    if match:
        flags = match.group(1).strip()
        query_without_flags = query[:match.start()].strip()
        return (query_without_flags, flags if flags else None)
    return (query, None)

@router.message(CursorCLIState.adding_flags)
async def handle_flags_input(message: Message, state: FSMContext, db_user: User):
    """Handle flags input after pressing Flags button."""
    text = message.text.strip()
    
    # Check for special commands first
    if text.casefold() == "/delete":
        await delete_current_session(message, state, db_user)
        return
    
    if text == "/exit":
        await exit_cursor_cli(message, state, db_user)
        return
    
    # Check if it's a session button (switching to another session)
    sessions = await get_user_sessions(db_user.id)
    session_names = [s.session_name for s in sessions]
    if text in session_names:
        # User is switching to another session
        await handle_session_button(message, state, db_user, text)
        return
    
    # Check if it's New Session button
    if text == NEW_SESSION_BUTTON:
        await state.set_state(CursorCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
        return
    
    if text == "/start" or text == BACK_TO_MAIN:
        # End current session before returning to main menu
        user_data = await state.get_data()
        session_uuid = user_data.get("session_uuid")
        if session_uuid:
            logger.info(f"Ending Cursor CLI session {session_uuid} before returning to main menu")
            await end_cursor_session(session_uuid)
        
        await state.clear()
        from .start import _show_main_menu
        await _show_main_menu(message, db_user, state)
        return
    
    user_data = await state.get_data()
    current_query = user_data.get("current_query", "")
    session_name = user_data.get("session_name")
    
    if not session_name:
        await message.answer("Ошибка: сессия не выбрана. Начните заново.")
        await state.clear()
        return
    
    # Add flags to query
    flags_text = message.text.strip()
    full_query = f"{current_query} #Flags {flags_text}" if current_query else f"#Flags {flags_text}"
    
    await state.update_data(current_query=full_query)
    await state.set_state(CursorCLIState.waiting_for_query)
    
    # Parse and execute
    query_clean, flags = parse_flags_from_query(full_query)
    
    # Get session from database
    db_session = await get_or_create_session(db_user.id, session_name)
    if not db_session:
        await message.answer("Ошибка: сессия не найдена. Создайте сессию заново.")
        await state.clear()
        return
    
    # Execute command with UUID (may be None for new sessions - will be set after first query)
    output, success, chat_id = await execute_cursor_command(db_session.uuid, query_clean, flags)
    
    # Update chat_id in database if we got one and it's not set yet
    if success and chat_id and not db_session.uuid:
        async with get_session() as update_session:
            update_result = await update_session.execute(
                select(CursorCLISession).where(CursorCLISession.id == db_session.id)
            )
            session_to_update = update_result.scalar_one_or_none()
            if session_to_update:
                session_to_update.uuid = chat_id
                await update_session.commit()
                await update_session.refresh(session_to_update)
                db_session.uuid = chat_id
                await state.update_data(session_uuid=chat_id)
                logger.info(f"Updated session '{session_name}' with chat_id: {chat_id}")
    
    # Save message
    await save_message(db_session.id, db_user.id, query_clean, output if success else None, flags)
    
    if success:
        await message.answer(f"**Сессия {session_name}:**\n\n{output}", parse_mode="Markdown")
    else:
        await message.answer(output)
    
    # Reset state
    await state.clear()

async def add_flags_button(message: Message, state: FSMContext, db_user: User):
    """Handle Flags button press during query input."""
    user_data = await state.get_data()
    current_query = user_data.get("current_query", "")
    
    # If query already has flags, show current state
    if "#flags" in current_query.lower():
        await message.answer(f"Текущий запрос:\n{current_query}\n\nВведите флаги для добавления:")
    else:
        # Add #Flags marker
        new_query = f"{current_query} #Flags " if current_query else "#Flags "
        await state.update_data(current_query=new_query)
        await message.answer(f"Добавьте флаги после #Flags:\n{new_query}")
    
    await state.set_state(CursorCLIState.adding_flags)

@router.message(CursorCLIState.waiting_for_query)
async def handle_query_input(message: Message, state: FSMContext, db_user: User):
    """Handle query input for CursorCLI session."""
    text = message.text.strip()
    
    # Check for special commands first (before any other processing)
    if text.casefold() == "/delete":
        await delete_current_session(message, state, db_user)
        return
    
    if text == "/exit":
        await exit_cursor_cli(message, state, db_user)
        return
    
    if text == "/start" or text == BACK_TO_MAIN:
        # End current session before returning to main menu
        user_data = await state.get_data()
        session_uuid = user_data.get("session_uuid")
        if session_uuid:
            logger.info(f"Ending Cursor CLI session {session_uuid} before returning to main menu")
            await end_cursor_session(session_uuid)
        
        await state.clear()
        from .start import _show_main_menu
        await _show_main_menu(message, db_user, state)
        return
    
    # Check if it's a session button (switching to another session) - BEFORE processing as query
    sessions = await get_user_sessions(db_user.id)
    session_names = [s.session_name for s in sessions]
    if text in session_names:
        # User is switching to another session
        await handle_session_button(message, state, db_user, text)
        return
    
    # Check if it's New Session button
    if text == NEW_SESSION_BUTTON:
        await state.set_state(CursorCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
        return
    
    user_data = await state.get_data()
    session_name = user_data.get("session_name")
    session_uuid = user_data.get("session_uuid")
    
    if not session_name:
        await message.answer("Ошибка: сессия не выбрана. Начните заново.")
        await state.clear()
        return
    
    # If UUID not in state, try to get it from database (but allow None for new sessions)
    if not session_uuid:
        db_session = await get_or_create_session(db_user.id, session_name)
        if not db_session:
            await message.answer("Ошибка: сессия не найдена. Создайте сессию заново.")
            await state.clear()
            return
        if db_session.uuid:
            session_uuid = db_session.uuid
            await state.update_data(session_uuid=session_uuid)
    
    query_text = message.text.strip()
    
    # Check if this is a host command (prefixed with !host or #host)
    # Examples: "!host ping 8.8.8.8" or "#host traceroute google.com"
    host_command_prefixes = ['!host', '#host', '!exec', '#exec']
    is_host_command = any(query_text.lower().startswith(prefix.lower()) for prefix in host_command_prefixes)
    
    if is_host_command:
        # Extract command after prefix
        host_command = None
        for prefix in host_command_prefixes:
            if query_text.lower().startswith(prefix.lower()):
                host_command = query_text[len(prefix):].strip()
                break
        
        if not host_command:
            await message.answer("❌ Ошибка: Команда не указана. Используйте: `!host <команда>`\n\nПример: `!host ping -c 4 8.8.8.8`")
            return
        
        # Execute on host
        await message.answer(f"🖥️ Выполняю команду на хосте: `{host_command}`")
        output, success = await execute_host_command_simple(host_command)
        
        if success:
            # Truncate very long output
            if len(output) > 4000:
                output = output[:4000] + "\n\n... (вывод обрезан, слишком длинный)"
            await message.answer(f"✅ Результат:\n```\n{output}\n```")
        else:
            await message.answer(f"❌ Ошибка выполнения:\n```\n{output}\n```")
        
        # Save to database
        db_session = await get_or_create_session(db_user.id, session_name)
        if db_session:
            await save_message(db_session.id, db_user.id, query_text, output if success else None, None)
        
        return
    
    # Save current query to state
    await state.update_data(current_query=query_text)
    
    # Check if query contains flags
    query_clean, flags = parse_flags_from_query(query_text)
    
    # Get session from database
    db_session = await get_or_create_session(db_user.id, session_name)
    if not db_session:
        await message.answer("Ошибка: сессия не найдена. Создайте сессию заново.")
        await state.clear()
        return
    
    # Execute command with UUID (may be None for new sessions - will be set after first query)
    output, success, chat_id = await execute_cursor_command(db_session.uuid, query_clean, flags)
    
    # Update chat_id in database if we got one and it's not set yet
    if success and chat_id and not db_session.uuid:
        async with get_session() as update_session:
            update_result = await update_session.execute(
                select(CursorCLISession).where(CursorCLISession.id == db_session.id)
            )
            session_to_update = update_result.scalar_one_or_none()
            if session_to_update:
                session_to_update.uuid = chat_id
                await update_session.commit()
                await update_session.refresh(session_to_update)
                db_session.uuid = chat_id
                await state.update_data(session_uuid=chat_id)
                logger.info(f"Updated session '{session_name}' with chat_id: {chat_id}")
    
    # Save message
    await save_message(db_session.id, db_user.id, query_clean, output if success else None, flags)
    
    if success:
        # Truncate long output
        if len(output) > 4000:
            output = output[:4000] + "\n\n... (вывод обрезан, слишком длинный)"
        await message.answer(f"**Сессия {session_name}:**\n\n{output}", parse_mode="Markdown")
    else:
        await message.answer(output)
    
    # Clear current_query from state and ask for next query
    await state.update_data(current_query="")
    await message.answer(f"Введите следующий запрос для сессии {session_name} или /exit для выхода:")

@router.message(CursorCLIState.waiting_for_session_name)
async def handle_session_name_input(message: Message, state: FSMContext, db_user: User):
    """Handle session name input for new session."""
    logger.info(f"handle_session_name_input: received '{message.text}' from user {db_user.id}")
    session_name = message.text.strip()
    
    # Validate session name (English, no spaces)
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_name):
        await message.answer("Название сессии должно содержать только английские буквы, цифры, дефисы и подчеркивания. Попробуйте снова:")
        return
    
    # Check if session already exists for this user
    existing = await get_or_create_session(db_user.id, session_name)
    if existing:
        await message.answer(f"Сессия '{session_name}' уже существует. Выберите её из меню или введите другое название:")
        return
    
    # Create session with UUID
    logger.info(f"Creating new session '{session_name}' for user {db_user.id}")
    await message.answer("Создаю сессию...")
    
    new_session, error = await create_session_with_uuid(db_user.id, session_name)
    
    if error:
        await message.answer(f"❌ {error}")
        return
    
    if not new_session:
        await message.answer("❌ Ошибка: не удалось создать сессию")
        return
    
    # Note: uuid may be None initially - it will be set on first query
    
    await state.update_data(session_name=session_name, session_uuid=new_session.uuid)
    await state.set_state(CursorCLIState.waiting_for_query)
    
    await message.answer(
        f"✅ Сессия '{session_name}' создана.\n\n"
        f"Введите запрос для сессии {session_name}:"
    )

async def show_cursor_cli_menu(message: Message, db_user: User, update_existing: bool = False):
    """Show CursorCLI submenu with sessions."""
    sessions = await get_user_sessions(db_user.id)
    keyboard = build_cursor_cli_menu(sessions)
    
    text = "**Cursor CLI**\n\nВыберите сессию или создайте новую:"
    if update_existing:
        # Update existing message instead of sending new one
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            # If edit fails, send new message
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Handler for menu button presses from CursorCLI submenu
async def handle_cursor_cli_button(message: Message, state: FSMContext, db_user: User):
    """Handle button press in CursorCLI submenu."""
    text = message.text.strip()
    logger.info(f"handle_cursor_cli_button: text='{text}', user_id={db_user.id}")
    
    current_state = await state.get_state()

    if text == NEW_SESSION_BUTTON:
        logger.info("New Session button pressed")
        await state.set_state(CursorCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
    elif text == FLAGS_BUTTON:
        if current_state == CursorCLIState.waiting_for_query:
            await add_flags_button(message, state, db_user)
        else:
            await message.answer("Сначала выберите сессию и введите запрос, затем можно добавить флаги.")
    elif text.casefold() == "/delete":
        # Handle /delete command even from submenu
        if current_state and str(current_state).startswith("CursorCLIState"):
            await delete_current_session(message, state, db_user)
        else:
            await message.answer("Команда /delete доступна только в активной сессии CursorCLI.")
    else:
        # Check if it's a session name
        sessions = await get_user_sessions(db_user.id)
        session_names = [s.session_name for s in sessions]
        if text in session_names:
            await handle_session_button(message, state, db_user, text)
        else:
            # If we're in waiting_for_query state, let the state handler process it
            if current_state == CursorCLIState.waiting_for_query:
                # Don't handle here, let handle_query_input process it
                return
            await message.answer("Неизвестная команда. Используйте кнопки меню.")

# Removed direct handlers for NEW_SESSION_BUTTON and FLAGS_BUTTON
# They are now handled through handle_cursor_cli_button() which is called from start.py
# when the context is correct (parent_id set or CursorCLIState active)

# Handler for session buttons will be in a separate function called from start.py
async def handle_session_button(message: Message, state: FSMContext, db_user: User, session_name: str):
    """Handle session name button press."""
    # End previous session if switching to another one
    user_data = await state.get_data()
    previous_session_uuid = user_data.get("session_uuid")
    if previous_session_uuid:
        logger.info(f"Ending previous Cursor CLI session {previous_session_uuid} before switching to {session_name}")
        await end_cursor_session(previous_session_uuid)
    
    # Verify session exists for this user and get UUID (may be None for new sessions)
    db_session = await get_or_create_session(db_user.id, session_name)
    
    if not db_session:
        await message.answer("Сессия не найдена. Выберите сессию из меню.")
        await show_cursor_cli_menu(message, db_user)
        return
    
    # Allow switching to session even if UUID is None (it will be set on first query)
    await state.update_data(session_name=session_name, session_uuid=db_session.uuid)
    await state.set_state(CursorCLIState.waiting_for_query)

    await message.answer(f"Введите запрос для сессии **{session_name}**:", parse_mode="Markdown")

@router.message(F.text.casefold() == "/exit")
async def exit_cursor_cli(message: Message, state: FSMContext, db_user: User):
    """Exit CursorCLI mode - only if in CursorCLI context."""
    current_state = await state.get_state()
    if current_state and "CursorCLIState" in str(current_state):
        # Get session UUID from state to end the session
        user_data = await state.get_data()
        session_uuid = user_data.get("session_uuid")
        
        # End the session if UUID is available
        if session_uuid:
            logger.info(f"Ending Cursor CLI session {session_uuid} for user {db_user.id}")
            await end_cursor_session(session_uuid)
        
        await state.clear()
        await message.answer("Режим Cursor CLI завершён. Используйте /start для возврата в меню.")
        from .start import _show_main_menu
        await _show_main_menu(message, db_user, state)

async def delete_current_session(message: Message, state: FSMContext, db_user: User):
    """Delete current CursorCLI session (removes button, keeps message logs)."""
    user_data = await state.get_data()
    session_name = user_data.get("session_name")
    session_uuid = user_data.get("session_uuid")
    
    if not session_name:
        await message.answer("Ошибка: текущая сессия не определена.")
        return
    
    # End Cursor CLI session if active
    if session_uuid:
        logger.info(f"Ending Cursor CLI session {session_uuid} before deletion")
        await end_cursor_session(session_uuid)
    
    # Delete session from database (messages remain, but session_id will become invalid)
    # Note: Due to foreign key constraints, we need to handle this carefully
    # If messages exist, we might need to set session_id to NULL or handle it differently
    async with get_session() as db_session:
        # Find session to delete
        result = await db_session.execute(
            select(CursorCLISession).where(
                and_(
                    CursorCLISession.user_id == db_user.id,
                    CursorCLISession.session_name == session_name
                )
            )
        )
        session_to_delete = result.scalar_one_or_none()
        
        if not session_to_delete:
            await message.answer(f"Сессия '{session_name}' не найдена.")
            await state.clear()
            await show_cursor_cli_menu(message, db_user)
            return
        
        # Check if there are messages for this session
        messages_result = await db_session.execute(
            select(CursorCLIMessage).where(
                CursorCLIMessage.session_id == session_to_delete.id
            )
        )
        messages_count = len(list(messages_result.scalars().all()))
        session_id_to_delete = session_to_delete.id
        
        # Delete the session
        # Messages will remain but their session_id will be set to NULL due to ondelete="SET NULL"
        # This preserves message logs while removing the session
        try:
            await db_session.delete(session_to_delete)
            await db_session.commit()
            logger.info(f"Deleted CursorCLI session '{session_name}' (id={session_id_to_delete}) for user {db_user.id}. Preserved {messages_count} messages with session_id set to NULL.")
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting session '{session_name}': {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при удалении сессии: {str(e)}")
            return
    
    # Get CursorCLI menu item ID to restore parent_id after clearing state
    async with get_session() as db_session:
        result = await db_session.execute(
            select(MenuItem).where(MenuItem.key == "SYSOPKA_CURSORCLI")
        )
        cursor_cli_menu_item = result.scalar_one_or_none()
    
    # Clear state but preserve menu_parent_id for proper button handling
    if cursor_cli_menu_item:
        await state.clear()
        await state.update_data(menu_parent_id=cursor_cli_menu_item.id)
    else:
        await state.clear()
    
    await show_cursor_cli_menu(message, db_user)
    await message.answer(f"✅ Сессия '{session_name}' удалена. История сообщений ({messages_count} сообщений) сохранена.")
