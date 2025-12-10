# app/routers/start.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from ..models import User, MenuItem
from ..db import get_session
from ..menu import build_main_menu

router = Router(name="start")

async def _get_menu_items_for_user(user: User) -> list[MenuItem]:
    async with get_session() as session:
        result = await session.execute(
            select(MenuItem)
            .where(MenuItem.is_active.is_(True), MenuItem.parent_id.is_(None))
            .order_by(MenuItem.sort_order, MenuItem.id)
        )
        items: list[MenuItem] = list(result.scalars().all())

    filtered: list[MenuItem] = []
    for item in items:
        roles = item.roles_list()
        if not roles or user.role in roles:
            filtered.append(item)

    return filtered

@router.message(F.text == "/start")
async def cmd_start(message: Message, db_user: User):
    items = await _get_menu_items_for_user(db_user)
    text = (
        f"Привет, {db_user.first_name or 'друг'}!\n\n"
        "Я домашний мультипользовательский бот.\n"
        "Кнопки меню зависят от твоих прав."
    )
    await message.answer(text, reply_markup=build_main_menu(db_user, items))

@router.callback_query(F.data.startswith("menu:"))
async def menu_router(callback: CallbackQuery, db_user: User):
    key = callback.data.split(":", maxsplit=1)[1]

    if key == "PROFILE":
        from .profile import show_profile
        await show_profile(callback.message, db_user)
        await callback.answer()
        return

    if key == "FAMILY_PANEL":
        if db_user.role != "superadmin":
            await callback.answer("Нет доступа.", show_alert=True)
            return
        await callback.message.answer("Здесь будет семейная панель (только для суперадминов).")
        await callback.answer()
        return

    await callback.answer("Пункт меню пока не реализован.", show_alert=True)

