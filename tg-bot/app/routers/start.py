# app/routers/start.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from ..models import User
from ..menu import build_menu_keyboard, get_menu_items_for_user, get_menu_item_by_label

router = Router(name="start")

async def _show_main_menu(message: Message, db_user: User, state: FSMContext | None = None):
    """Show main menu to user."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Clear parent_id when showing main menu
    if state:
        await state.update_data(menu_parent_id=None)
    
    items = await get_menu_items_for_user(db_user, parent_id=None)
    logger.info(f"Building main menu with {len(items)} items for user {db_user.id}")
    for item in items:
        logger.info(f"Menu item: {item.key} - {item.label}")
    text = (
        f"Привет, {db_user.first_name or 'друг'}!\n\n"
        "Я домашний мультипользовательский бот.\n"
        "Кнопки меню зависят от твоих прав."
    )
    await message.answer(text, reply_markup=build_menu_keyboard(items, back_button=False))

@router.message(F.text == "/start")
async def cmd_start(message: Message, db_user: User, state: FSMContext):
    await _show_main_menu(message, db_user, state)

@router.message(F.text == "/update")
async def cmd_update(message: Message, db_user: User, state: FSMContext):
    """Update menu without restarting bot."""
    await _show_main_menu(message, db_user, state)
    await message.answer("✅ Меню обновлено!")

@router.message(F.text == "◀️ Главное меню")
async def cmd_back_to_main(message: Message, db_user: User, state: FSMContext):
    """Return to main menu from submenu."""
    await state.clear()
    await _show_main_menu(message, db_user, state)

@router.message(F.text)
async def menu_text_router(message: Message, db_user: User, state: FSMContext):
    """Handle menu button presses. Supports main menu and submenus."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"menu_text_router received text: '{message.text}' from user {db_user.telegram_id}")

    # FIRST: Check if this is a main menu button - if so, clear state and process normally
    # This must be done BEFORE checking ClaudeCLI state, so main menu buttons always work
    main_menu_items = await get_menu_items_for_user(db_user, parent_id=None)
    main_menu_labels = [item.label for item in main_menu_items]
    
    if message.text in main_menu_labels:
        logger.info(f"Main menu button '{message.text}' pressed, clearing FSM state")
        await state.clear()
        await state.update_data(menu_parent_id=None)
        # Continue processing below as normal menu button - don't return here
    
    # Check current state - if in ClaudeCLI or CursorCLI state and NOT a main menu button, skip entirely
    # cli routers are registered BEFORE start_router, so their state handlers should catch it first
    current_state = await state.get_state()
    if current_state and ("ClaudeCLIState" in str(current_state) or "CursorCLIState" in str(current_state)) and message.text not in main_menu_labels:
        logger.info(f"In CLI state ({current_state}), skipping menu_text_router - cli router should handle it")
        return  # Skip processing - cli router should handle it (it's registered first)
    
    # Check if we're in a submenu (state contains parent_id)
    user_data = await state.get_data()
    parent_id = user_data.get("menu_parent_id")
    
    logger.info(f"Current state: {current_state}, parent_id: {parent_id}")
    
    # Check if we're in ClaudeCLI, CursorCLI or ChatGPT CLI submenu (check parent_id only, not state - state is handled above)
    is_claude_cli_context = False
    is_cursor_cli_context = False
    is_chatgpt_cli_context = False
    
    if parent_id:
        from sqlalchemy import select
        from ..db import get_session
        from ..models import MenuItem
        async with get_session() as session:
            parent_result = await session.execute(
                select(MenuItem).where(MenuItem.id == parent_id)
            )
            parent_item = parent_result.scalar_one_or_none()
            if parent_item:
                if parent_item.key == "SYSOPKA_CLAUDECLI":
                    is_claude_cli_context = True
                    logger.info("Detected ClaudeCLI parent_id context")
                elif parent_item.key == "SYSOPKA_CURSORCLI":
                    is_cursor_cli_context = True
                    logger.info("Detected CursorCLI parent_id context")
                elif parent_item.key == "SYSOPKA_CHATGPT":
                    is_chatgpt_cli_context = True
                    logger.info("Detected ChatGPT CLI parent_id context")
    
    if is_claude_cli_context:
        # Handle ClaudeCLI submenu buttons (but not state handlers - those are in claude_cli router)
        logger.info("Handling as ClaudeCLI button")
        from .claude_cli import handle_claude_cli_button
        await handle_claude_cli_button(message, state, db_user)
        return
    
    if is_cursor_cli_context:
        # Handle CursorCLI submenu buttons (but not state handlers - those are in cursor_cli router)
        logger.info("Handling as CursorCLI button")
        from .cursor_cli import handle_cursor_cli_button
        await handle_cursor_cli_button(message, state, db_user)
        return
    
    if is_chatgpt_cli_context:
        # Handle ChatGPT CLI submenu buttons (but not state handlers - those are in chatgpt_cli router)
        logger.info("Handling as ChatGPT CLI button")
        from .chatgpt_cli import handle_chatgpt_cli_button
        await handle_chatgpt_cli_button(message, state, db_user)
        return
    
    # Find menu item
    logger.info(f"Searching menu item for text: '{message.text}', parent_id: {parent_id}")
    item = await get_menu_item_by_label(message.text, db_user, parent_id=parent_id)
    if not item:
        logger.warning(f"No menu item found for text: '{message.text}' parent_id={parent_id}")
        return
    
    logger.info(f"Found menu item: key={item.key}, action_type={item.action_type}")

    # Handle different action types
    if item.action_type == "submenu":
        # Show submenu
        children = await get_menu_items_for_user(db_user, parent_id=item.id)
        if not children:
            await message.answer("Подменю пустое.")
            return
        await state.update_data(menu_parent_id=item.id)
        logger.info(f"Showing submenu for {item.key} with {len(children)} items")
        await message.answer(
            f"{item.label}",
            reply_markup=build_menu_keyboard(children, back_button=True)
        )
    elif item.action_type == "claude_cli_submenu":
        # Handle ClaudeCLI submenu
        from .claude_cli import show_claude_cli_menu
        # Set parent_id to indicate we're in ClaudeCLI submenu
        await state.update_data(menu_parent_id=item.id)
        await show_claude_cli_menu(message, db_user)
    elif item.action_type == "cursor_cli_submenu":
        # Handle CursorCLI submenu
        from .cursor_cli import show_cursor_cli_menu
        # Set parent_id to indicate we're in CursorCLI submenu
        await state.update_data(menu_parent_id=item.id)
        await show_cursor_cli_menu(message, db_user)
    elif item.action_type == "chatgpt_cli_submenu":
        # Handle ChatGPT CLI submenu
        from .chatgpt_cli import show_chatgpt_cli_menu
        # Set parent_id to indicate we're in ChatGPT CLI submenu
        await state.update_data(menu_parent_id=item.id)
        await show_chatgpt_cli_menu(message, db_user)
    elif item.action_type == "agent":
        # Handle Agent
        from .agent import start_agent
        await start_agent(message, state, db_user)
    elif item.action_type == "flowise_agentflow":
        # Handle agentflow action
        agentflow_id = item.get_agentflow_id()
        if not agentflow_id:
            await message.answer("Ошибка: agentflow ID не настроен.")
            return
        
        # Sysopka submenu items
        if item.key.startswith("SYSOPKA_"):
            sysopka_type = item.key.lower().replace("sysopka_", "")
            from .sysopka import _start_sysopka_chat
            await _start_sysopka_chat(message, state, db_user, sysopka_type, agentflow_id)
        else:
            await message.answer(f"Действие '{item.label}' еще не реализовано.")
    elif item.action_type == "profile":
        # Show profile
        from .profile import show_profile
        await show_profile(message, db_user)
    else:
        await message.answer(f"Действие '{item.label}' еще не реализовано.")
