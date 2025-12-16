# app/menu.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from typing import Iterable
from sqlalchemy import select

from .models import User, MenuItem
from .db import get_session

async def get_menu_items_for_user(user: User, parent_id: int | None = None) -> list[MenuItem]:
    """Get menu items for user, optionally filtered by parent_id."""
    async with get_session() as session:
        query = select(MenuItem).where(
            MenuItem.is_active.is_(True),
            MenuItem.parent_id == parent_id
        ).order_by(MenuItem.sort_order, MenuItem.id)
        result = await session.execute(query)
        items: list[MenuItem] = list(result.scalars().all())

    # Filter by user roles
    filtered: list[MenuItem] = []
    for item in items:
        roles = item.roles_list()
        if not roles or user.role in roles:
            filtered.append(item)
    return filtered

async def get_menu_item_by_label(text: str, user: User, parent_id: int | None = None) -> MenuItem | None:
    """Find menu item by label text, optionally filtered by parent_id."""
    import logging
    logger = logging.getLogger(__name__)
    text = (text or "").strip()
    if not text:
        return None
    logger.info(f"Searching menu item: label='{text}', parent_id={parent_id}, user_role={user.role}")
    async with get_session() as session:
        query = select(MenuItem).where(
            MenuItem.label == text,
            MenuItem.is_active.is_(True),
            MenuItem.parent_id == parent_id
        )
        result = await session.execute(query)
        item = result.scalar_one_or_none()
    if not item:
        logger.warning(f"Menu item not found for label='{text}', parent_id={parent_id}")
        return None
    # Check user roles
    roles = item.roles_list()
    if roles and user.role not in roles:
        logger.warning(f"User {user.id} role {user.role} not in {roles} for item {item.key}")
        return None
    logger.info(f"Found menu item: {item.key} - {item.label}")
    return item

def build_menu_keyboard(items: Iterable[MenuItem], back_button: bool = False) -> ReplyKeyboardMarkup:
    """Build keyboard markup from menu items. Items are arranged in rows."""
    keyboard_rows: list[list[KeyboardButton]] = []
    
    # Group items into rows (2 buttons per row for better layout)
    items_list = list(items)
    i = 0
    while i < len(items_list):
        row = []
        # Add up to 2 buttons per row
        for _ in range(min(2, len(items_list) - i)):
            item = items_list[i]
            row.append(KeyboardButton(text=item.label))
            i += 1
        if row:
            keyboard_rows.append(row)
    
    # Add back button if needed
    if back_button:
        keyboard_rows.append([KeyboardButton(text="◀️ Главное меню")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )
