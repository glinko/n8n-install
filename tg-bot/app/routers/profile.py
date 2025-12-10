# app/routers/profile.py
from aiogram import Router
from aiogram.types import Message
from ..models import User

router = Router(name="profile")

async def show_profile(message: Message, db_user: User):
    text = (
        "👤 *Твой профиль*\n\n"
        f"ID: `{db_user.telegram_id}`\n"
        f"Имя: {db_user.first_name or ''} {db_user.last_name or ''}\n"
        f"Username: @{db_user.username or '-'}\n"
        f"Роль: `{db_user.role}`\n"
        f"Язык: `{db_user.language_code}`\n"
    )
    await message.answer(text, parse_mode="Markdown")

