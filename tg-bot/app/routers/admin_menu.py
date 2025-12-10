# app/routers/admin_menu.py
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select
from ..db import get_session
from ..models import User, MenuItem

router = Router(name="admin_menu")

def is_superadmin(u: User) -> bool:
    return u.role == "superadmin"

@router.message(F.text.startswith("/menu_list"))
async def cmd_menu_list(message: Message, db_user: User):
    if not is_superadmin(db_user):
        await message.answer("Недостаточно прав.")
        return

    async with get_session() as session:
        result = await session.execute(
            select(MenuItem)
            .where(MenuItem.parent_id.is_(None))
            .order_by(MenuItem.sort_order, MenuItem.id)
        )
        items: list[MenuItem] = list(result.scalars().all())

    if not items:
        await message.answer("Меню пока пустое.")
        return

    lines = []
    for m in items:
        lines.append(
            f"*{m.key}* — \"{m.label}\" | roles: `{m.roles or '-'}` | "
            f"active: `{m.is_active}` | sort: {m.sort_order}"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(F.text.startswith("/menu_add"))
async def cmd_menu_add(message: Message, db_user: User):
    if not is_superadmin(db_user):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=4)
    if len(parts) < 5:
        await message.answer(
            "Формат: /menu_add <KEY> <label_с_подчёркиваниями> <roles> <sort_order>\n"
            "Пример: /menu_add STATS Статистика user,superadmin 20"
        )
        return

    _, key, label_raw, roles, sort_raw = parts
    label = label_raw.replace("_", " ")

    try:
        sort_order = int(sort_raw)
    except ValueError:
        await message.answer("sort_order должен быть числом.")
        return

    async with get_session() as session:
        result = await session.execute(
            select(MenuItem).where(MenuItem.key == key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            await message.answer("Элемент с таким KEY уже существует.")
            return

        item = MenuItem(
            key=key,
            label=label,
            roles=roles if roles != "-" else None,
            sort_order=sort_order,
            is_active=True,
            parent_id=None,
        )
        session.add(item)
        await session.commit()

    await message.answer(f"Элемент меню `{key}` добавлен.\nНе забудь реализовать обработку key={key} в коде.")

@router.message(F.text.startswith("/menu_set_roles"))
async def cmd_menu_set_roles(message: Message, db_user: User):
    if not is_superadmin(db_user):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /menu_set_roles <KEY> <roles>\nroles = 'user,superadmin' или '-'")
        return

    _, key, roles = parts

    async with get_session() as session:
        result = await session.execute(
            select(MenuItem).where(MenuItem.key == key)
        )
        item = result.scalar_one_or_none()
        if not item:
            await message.answer("Элемент не найден.")
            return

        item.roles = None if roles == "-" else roles
        session.add(item)
        await session.commit()

    await message.answer(f"Роли для `{key}` обновлены: `{roles}`.")

@router.message(F.text.startswith("/menu_toggle"))
async def cmd_menu_toggle(message: Message, db_user: User):
    if not is_superadmin(db_user):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /menu_toggle <KEY>")
        return

    _, key = parts

    async with get_session() as session:
        result = await session.execute(
            select(MenuItem).where(MenuItem.key == key)
        )
        item = result.scalar_one_or_none()
        if not item:
            await message.answer("Элемент не найден.")
            return

        item.is_active = not item.is_active
        session.add(item)
        await session.commit()

    await message.answer(f"Элемент `{key}` теперь is_active={item.is_active}. Нажми /start, чтобы обновить меню.")

