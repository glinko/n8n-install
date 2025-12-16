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
from ..models import User, ClaudeCLISession, ClaudeCLIMessage, MenuItem
from ..states.claude_cli import ClaudeCLIState
from ..menu import build_menu_keyboard
from ..services.host_executor import execute_host_command_simple, ALLOWED_HOST_COMMANDS

router = Router(name="claude_cli")
logger = logging.getLogger(__name__)

NEW_SESSION_BUTTON = "New Session"
FLAGS_BUTTON = "Flags"
BACK_TO_MAIN = "◀️ Главное меню"

# Note: BACK_TO_MAIN button is handled in start.py, not here
# to avoid conflicts with main menu handling

def build_claude_cli_menu(sessions: list[ClaudeCLISession]) -> ReplyKeyboardMarkup:
    """Build ClaudeCLI submenu with sessions."""
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

async def get_user_sessions(user_id: int) -> list[ClaudeCLISession]:
    """Get all ClaudeCLI sessions for user."""
    async with get_session() as session:
        result = await session.execute(
            select(ClaudeCLISession)
            .where(ClaudeCLISession.user_id == user_id)
            .order_by(ClaudeCLISession.created_at.desc())
        )
        return list(result.scalars().all())

async def create_session_with_uuid(user_id: int, session_name: str) -> tuple[ClaudeCLISession, str | None]:
    """
    Create new Claude CLI session by executing command with --output-format json.
    Returns (session, error_message).
    """
    try:
        # Execute command to create session and get UUID
        # Command: docker exec claude-code-console claude chat --output-format json "SESSION_NAME" --permission-mode bypassPermissions
        client = docker.from_env()
        cmd = ['claude', 'chat', '--output-format', 'json', '--permission-mode', 'bypassPermissions', session_name]
        
        logger.info(f"Creating Claude CLI session: docker exec claude-code-console {' '.join(cmd)}")
        
        loop = asyncio.get_event_loop()
        container = await loop.run_in_executor(None, lambda: client.containers.get('claude-code-console'))
        exec_result = await loop.run_in_executor(
            None,
            lambda: container.exec_run(cmd, stdout=True, stderr=True, user='claude')
        )
        
        if exec_result.exit_code != 0:
            error_msg = exec_result.output.decode('utf-8', errors='replace')
            logger.error(f"Failed to create session: {error_msg}")
            return (None, f"Ошибка создания сессии:\n{error_msg}")
        
        # Parse JSON response to get UUID
        output = exec_result.output.decode('utf-8', errors='replace')
        try:
            # Try to find JSON in output (might have extra text)
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                response_data = json.loads(json_str)
                # Use session_id for resume, not uuid
                session_id_value = response_data.get('session_id')
                uuid_value = response_data.get('uuid')  # Keep uuid for reference
                
                if not session_id_value:
                    logger.error(f"No session_id in response: {response_data}")
                    return (None, "Ошибка: session_id не найден в ответе Claude CLI")
                
                # Save session to database (store session_id as uuid field for resume)
                async with get_session() as db_session:
                    new_session = ClaudeCLISession(
                        user_id=user_id,
                        session_name=session_name,
                        uuid=session_id_value  # Store session_id for resume
                    )
                    db_session.add(new_session)
                    await db_session.commit()
                    await db_session.refresh(new_session)
                    logger.info(f"Created session '{session_name}' with session_id: {session_id_value}")
                    return (new_session, None)
            else:
                logger.error(f"No JSON found in output: {output[:200]}")
                return (None, f"Ошибка: не удалось найти JSON в ответе:\n{output[:500]}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}, output: {output[:200]}")
            return (None, f"Ошибка парсинга JSON:\n{output[:500]}")
            
    except docker.errors.NotFound:
        logger.error("Container 'claude-code-console' not found")
        return (None, "Ошибка: контейнер 'claude-code-console' не найден")
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        return (None, f"Ошибка Docker API: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating Claude CLI session: {e}", exc_info=True)
        return (None, f"Ошибка создания сессии: {str(e)}")

async def get_or_create_session(user_id: int, session_name: str) -> ClaudeCLISession:
    """Get existing session or return None (sessions must be created via create_session_with_uuid)."""
    async with get_session() as session:
        result = await session.execute(
            select(ClaudeCLISession).where(
                and_(
                    ClaudeCLISession.user_id == user_id,
                    ClaudeCLISession.session_name == session_name
                )
            )
        )
        existing = result.scalar_one_or_none()
        return existing

async def save_message(session_id: int, user_id: int, query: str, response: str | None = None, flags_used: str | None = None):
    """Save ClaudeCLI message to database."""
    async with get_session() as session:
        msg = ClaudeCLIMessage(
            session_id=session_id,
            user_id=user_id,
            query=query,
            response=response,
            flags_used=flags_used
        )
        session.add(msg)
        await session.commit()

async def execute_claude_command(session_uuid: str, query: str, flags: str | None = None) -> tuple[str, bool]:
    """
    Execute docker exec command for Claude CLI using Docker API with resume (-r) flag.
    Returns (output, success).
    
    Command format: docker exec claude-code-console claude chat -r "UUID" "QUERY" [FLAGS]
    """
    try:
        # Connect to Docker daemon (uses DOCKER_HOST env or /var/run/docker.sock)
        client = docker.from_env()
        
        # Build command with -r (resume) flag and --print for non-interactive mode
        # Query must be passed via stdin using echo and pipe
        # Escape single quotes in query for shell
        query_escaped = query.replace("'", "'\\''")
        
        # Build command string with echo and pipe
        # Add --permission-mode bypassPermissions to skip permission prompts
        base_cmd = f"echo '{query_escaped}' | claude chat -r {shlex.quote(session_uuid)} --print --permission-mode bypassPermissions"
        
        # Add flags if provided (after --print, before --permission-mode)
        if flags and flags.strip():
            flags_clean = flags.strip()
            base_cmd = f"echo '{query_escaped}' | claude chat -r {shlex.quote(session_uuid)} --print {flags_clean} --permission-mode bypassPermissions"
        
        logger.info(f"Executing Claude CLI command: docker exec claude-code-console {base_cmd}")
        
        loop = asyncio.get_event_loop()
        container = await loop.run_in_executor(None, lambda: client.containers.get('claude-code-console'))
        
        # Execute with shell=True to use pipe
        # Use sh -c to execute shell command (works with older Docker SDK versions)
        exec_result = await loop.run_in_executor(
            None,
            lambda: container.exec_run(
                ['sh', '-c', base_cmd],
                stdout=True,
                stderr=True,
                user='claude'
            )
        )
        
        if exec_result.exit_code == 0:
            output = exec_result.output.decode('utf-8', errors='replace')
            return (output, True)
        else:
            error_msg = exec_result.output.decode('utf-8', errors='replace')
            return (f"Ошибка выполнения команды:\n{error_msg}", False)
            
    except docker.errors.NotFound:
        logger.error("Container 'claude-code-console' not found")
        return ("Ошибка: контейнер 'claude-code-console' не найден", False)
    except docker.errors.APIError as e:
        logger.error(f"Docker API error: {e}")
        return (f"Ошибка Docker API: {str(e)}", False)
    except Exception as e:
        logger.error(f"Error executing Claude CLI command: {e}", exc_info=True)
        return (f"Ошибка выполнения команды: {str(e)}", False)

async def end_claude_session(session_uuid: str) -> bool:
    """
    End Claude CLI session by sending /exit command via stdin.
    Returns True if successful.
    """
    try:
        client = docker.from_env()
        # Send /exit to end the session via stdin
        # Use bypassPermissions to avoid prompts during exit
        cmd_str = f"echo '/exit' | claude chat -r {shlex.quote(session_uuid)} --print --permission-mode bypassPermissions"
        
        logger.info(f"Ending Claude CLI session: docker exec claude-code-console {cmd_str}")
        
        loop = asyncio.get_event_loop()
        container = await loop.run_in_executor(None, lambda: client.containers.get('claude-code-console'))
        # Use sh -c to execute shell command (works with older Docker SDK versions)
        exec_result = await loop.run_in_executor(
            None,
            lambda: container.exec_run(['sh', '-c', cmd_str], stdout=True, stderr=True, user='claude')
        )
        
        return exec_result.exit_code == 0
    except Exception as e:
        logger.error(f"Error ending Claude CLI session: {e}", exc_info=True)
        return False

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

@router.message(ClaudeCLIState.adding_flags)
async def handle_flags_input(message: Message, state: FSMContext, db_user: User):
    """Handle flags input after pressing Flags button."""
    text = message.text.strip()
    
    # Check for special commands first
    if text.casefold() == "/delete":
        await delete_current_session(message, state, db_user)
        return
    
    if text == "/exit":
        await exit_claude_cli(message, state, db_user)
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
        await state.set_state(ClaudeCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
        return
    
    if text == "/start" or text == BACK_TO_MAIN:
        # End current session before returning to main menu
        user_data = await state.get_data()
        session_uuid = user_data.get("session_uuid")
        if session_uuid:
            logger.info(f"Ending Claude CLI session {session_uuid} before returning to main menu")
            await end_claude_session(session_uuid)
        
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
    await state.set_state(ClaudeCLIState.waiting_for_query)
    
    # Parse and execute
    query_clean, flags = parse_flags_from_query(full_query)
    
    # Get session from database
    db_session = await get_or_create_session(db_user.id, session_name)
    if not db_session or not db_session.uuid:
        await message.answer("Ошибка: UUID сессии не найден. Создайте сессию заново.")
        await state.clear()
        return
    
    # Execute command with UUID
    output, success = await execute_claude_command(db_session.uuid, query_clean, flags)
    
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
    
    await state.set_state(ClaudeCLIState.adding_flags)

@router.message(ClaudeCLIState.waiting_for_query)
async def handle_query_input(message: Message, state: FSMContext, db_user: User):
    """Handle query input for ClaudeCLI session."""
    text = message.text.strip()
    
    # Check for special commands first (before any other processing)
    if text.casefold() == "/delete":
        await delete_current_session(message, state, db_user)
        return
    
    if text == "/exit":
        await exit_claude_cli(message, state, db_user)
        return
    
    if text == "/start" or text == BACK_TO_MAIN:
        # End current session before returning to main menu
        user_data = await state.get_data()
        session_uuid = user_data.get("session_uuid")
        if session_uuid:
            logger.info(f"Ending Claude CLI session {session_uuid} before returning to main menu")
            await end_claude_session(session_uuid)
        
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
        await state.set_state(ClaudeCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
        return
    
    user_data = await state.get_data()
    session_name = user_data.get("session_name")
    session_uuid = user_data.get("session_uuid")
    
    if not session_name:
        await message.answer("Ошибка: сессия не выбрана. Начните заново.")
        await state.clear()
        return
    
    # If UUID not in state, get it from database
    if not session_uuid:
        db_session = await get_or_create_session(db_user.id, session_name)
        if not db_session or not db_session.uuid:
            await message.answer("Ошибка: UUID сессии не найден. Создайте сессию заново.")
            await state.clear()
            return
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
    if not db_session or not db_session.uuid:
        await message.answer("Ошибка: UUID сессии не найден. Создайте сессию заново.")
        await state.clear()
        return
    
    # Execute command with UUID
    output, success = await execute_claude_command(db_session.uuid, query_clean, flags)
    
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

@router.message(ClaudeCLIState.waiting_for_session_name)
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
    
    if not new_session or not new_session.uuid:
        await message.answer("❌ Ошибка: не удалось получить UUID сессии")
        return
    
    await state.update_data(session_name=session_name, session_uuid=new_session.uuid)
    await state.set_state(ClaudeCLIState.waiting_for_query)
    
    await message.answer(
        f"✅ Сессия '{session_name}' создана.\n\n"
        f"Введите запрос для сессии {session_name}:"
    )

async def show_claude_cli_menu(message: Message, db_user: User, update_existing: bool = False):
    """Show ClaudeCLI submenu with sessions."""
    sessions = await get_user_sessions(db_user.id)
    keyboard = build_claude_cli_menu(sessions)
    
    text = "**Claude CLI**\n\nВыберите сессию или создайте новую:"
    if update_existing:
        # Update existing message instead of sending new one
        try:
            await message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except:
            # If edit fails, send new message
            await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# Handler for menu button presses from ClaudeCLI submenu
async def handle_claude_cli_button(message: Message, state: FSMContext, db_user: User):
    """Handle button press in ClaudeCLI submenu."""
    text = message.text.strip()
    logger.info(f"handle_claude_cli_button: text='{text}', user_id={db_user.id}")
    
    current_state = await state.get_state()

    if text == NEW_SESSION_BUTTON:
        logger.info("New Session button pressed")
        await state.set_state(ClaudeCLIState.waiting_for_session_name)
        await message.answer("Название новой сессии (на английском без пробелов):")
    elif text == FLAGS_BUTTON:
        if current_state == ClaudeCLIState.waiting_for_query:
            await add_flags_button(message, state, db_user)
        else:
            await message.answer("Сначала выберите сессию и введите запрос, затем можно добавить флаги.")
    elif text.casefold() == "/delete":
        # Handle /delete command even from submenu
        if current_state and str(current_state).startswith("ClaudeCLIState"):
            await delete_current_session(message, state, db_user)
        else:
            await message.answer("Команда /delete доступна только в активной сессии ClaudeCLI.")
    else:
        # Check if it's a session name
        sessions = await get_user_sessions(db_user.id)
        session_names = [s.session_name for s in sessions]
        if text in session_names:
            await handle_session_button(message, state, db_user, text)
        else:
            # If we're in waiting_for_query state, let the state handler process it
            if current_state == ClaudeCLIState.waiting_for_query:
                # Don't handle here, let handle_query_input process it
                return
            await message.answer("Неизвестная команда. Используйте кнопки меню.")

# Removed direct handlers for NEW_SESSION_BUTTON and FLAGS_BUTTON
# They are now handled through handle_claude_cli_button() which is called from start.py
# when the context is correct (parent_id set or ClaudeCLIState active)

# Handler for session buttons will be in a separate function called from start.py
async def handle_session_button(message: Message, state: FSMContext, db_user: User, session_name: str):
    """Handle session name button press."""
    # End previous session if switching to another one
    user_data = await state.get_data()
    previous_session_uuid = user_data.get("session_uuid")
    if previous_session_uuid:
        logger.info(f"Ending previous Claude CLI session {previous_session_uuid} before switching to {session_name}")
        await end_claude_session(previous_session_uuid)
    
    # Verify session exists for this user and get UUID
    db_session = await get_or_create_session(db_user.id, session_name)
    
    if not db_session:
        await message.answer("Сессия не найдена. Выберите сессию из меню.")
        await show_claude_cli_menu(message, db_user)
        return
    
    if not db_session.uuid:
        await message.answer("Ошибка: UUID сессии не найден. Создайте сессию заново.")
        await show_claude_cli_menu(message, db_user)
        return

    await state.update_data(session_name=session_name, session_uuid=db_session.uuid)
    await state.set_state(ClaudeCLIState.waiting_for_query)

    await message.answer(f"Введите запрос для сессии **{session_name}**:", parse_mode="Markdown")

@router.message(F.text.casefold() == "/exit")
async def exit_claude_cli(message: Message, state: FSMContext, db_user: User):
    """Exit ClaudeCLI mode - only if in ClaudeCLI context."""
    current_state = await state.get_state()
    if current_state and "ClaudeCLIState" in str(current_state):
        # Get session UUID from state to end the session
        user_data = await state.get_data()
        session_uuid = user_data.get("session_uuid")
        
        # End the session if UUID is available
        if session_uuid:
            logger.info(f"Ending Claude CLI session {session_uuid} for user {db_user.id}")
            await end_claude_session(session_uuid)
        
        await state.clear()
        await message.answer("Режим Claude CLI завершён. Используйте /start для возврата в меню.")
        from .start import _show_main_menu
        await _show_main_menu(message, db_user, state)

async def delete_current_session(message: Message, state: FSMContext, db_user: User):
    """Delete current ClaudeCLI session (removes button, keeps message logs)."""
    user_data = await state.get_data()
    session_name = user_data.get("session_name")
    session_uuid = user_data.get("session_uuid")
    
    if not session_name:
        await message.answer("Ошибка: текущая сессия не определена.")
        return
    
    # End Claude CLI session if active
    if session_uuid:
        logger.info(f"Ending Claude CLI session {session_uuid} before deletion")
        await end_claude_session(session_uuid)
    
    # Delete session from database (messages remain, but session_id will become invalid)
    # Note: Due to foreign key constraints, we need to handle this carefully
    # If messages exist, we might need to set session_id to NULL or handle it differently
    async with get_session() as db_session:
        # Find session to delete
        result = await db_session.execute(
            select(ClaudeCLISession).where(
                and_(
                    ClaudeCLISession.user_id == db_user.id,
                    ClaudeCLISession.session_name == session_name
                )
            )
        )
        session_to_delete = result.scalar_one_or_none()
        
        if not session_to_delete:
            await message.answer(f"Сессия '{session_name}' не найдена.")
            await state.clear()
            await show_claude_cli_menu(message, db_user)
            return
        
        # Check if there are messages for this session
        messages_result = await db_session.execute(
            select(ClaudeCLIMessage).where(
                ClaudeCLIMessage.session_id == session_to_delete.id
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
            logger.info(f"Deleted ClaudeCLI session '{session_name}' (id={session_id_to_delete}) for user {db_user.id}. Preserved {messages_count} messages with session_id set to NULL.")
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting session '{session_name}': {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при удалении сессии: {str(e)}")
            return
    
    # Get ClaudeCLI menu item ID to restore parent_id after clearing state
    async with get_session() as db_session:
        result = await db_session.execute(
            select(MenuItem).where(MenuItem.key == "SYSOPKA_CLAUDECLI")
        )
        claude_cli_menu_item = result.scalar_one_or_none()
    
    # Clear state but preserve menu_parent_id for proper button handling
    if claude_cli_menu_item:
        await state.clear()
        await state.update_data(menu_parent_id=claude_cli_menu_item.id)
    else:
        await state.clear()
    
    await show_claude_cli_menu(message, db_user)
    await message.answer(f"✅ Сессия '{session_name}' удалена. История сообщений ({messages_count} сообщений) сохранена.")
