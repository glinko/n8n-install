# app/routers/admin.py
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select
from ..models import User
from ..db import get_session

router = Router(name="admin")

def is_superadmin(user: User) -> bool:
    return user.role == "superadmin"

@router.message(F.text.startswith("/users"))
async def cmd_users(message: Message, db_user: User):
    if not is_superadmin(db_user):
        await message.answer("Недостаточно прав.")
        return

    async with get_session() as session:
        result = await session.execute(select(User).order_by(User.id).limit(50))
        users = result.scalars().all()

    if not users:
        await message.answer("Пользователей пока нет.")
        return

    lines = []
    for u in users:
        lines.append(
            f"{u.id}: {u.telegram_id} @{u.username or '-'} ({u.role})"
        )

    await message.answer("Первые пользователи:\n" + "\n".join(lines))

@router.message(F.text.startswith("/setrole"))
async def cmd_setrole(message: Message, db_user: User):
    if not is_superadmin(db_user):
        await message.answer("Недостаточно прав.")
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Формат: /setrole <telegram_id> <role>")
        return

    try:
        target_tid = int(parts[1])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    new_role = parts[2]

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == target_tid)
        )
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден.")
            return

        user.role = new_role
        session.add(user)
        await session.commit()

    await message.answer(f"Роль пользователя {target_tid} изменена на `{new_role}`.")

