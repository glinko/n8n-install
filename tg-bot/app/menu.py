# app/menu.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Iterable
from .models import User, MenuItem

def build_main_menu(user: User, items: Iterable[MenuItem]) -> InlineKeyboardMarkup:
    keyboard_rows: list[list[InlineKeyboardButton]] = []

    for item in items:
        cb_data = f"menu:{item.key}"
        keyboard_rows.append(
            [InlineKeyboardButton(text=item.label, callback_data=cb_data)]
        )

    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

