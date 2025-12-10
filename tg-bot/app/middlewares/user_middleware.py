# app/middlewares/user_middleware.py
from typing import Callable, Awaitable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery
from sqlalchemy import select
from ..db import get_session
from ..models import User, UserEvent
from ..config import settings

class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = None
        message: Message | None = None
        callback: CallbackQuery | None = None

        if event.message:
            message = event.message
            tg_user = event.message.from_user
        elif event.callback_query:
            callback = event.callback_query
            tg_user = event.callback_query.from_user
        else:
            return await handler(event, data)

        if not tg_user:
            return await handler(event, data)

        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            )
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                    language_code=tg_user.language_code,
                )
                if tg_user.id in settings.superadmin_ids:
                    user.role = "superadmin"
                session.add(user)
                await session.flush()
            else:
                dirty = False
                if user.username != tg_user.username:
                    user.username = tg_user.username
                    dirty = True
                if user.first_name != tg_user.first_name:
                    user.first_name = tg_user.first_name
                    dirty = True
                if user.last_name != tg_user.last_name:
                    user.last_name = tg_user.last_name
                    dirty = True
                if user.language_code != tg_user.language_code:
                    user.language_code = tg_user.language_code
                    dirty = True
                if tg_user.id in settings.superadmin_ids and user.role != "superadmin":
                    user.role = "superadmin"
                    dirty = True
                if dirty:
                    session.add(user)

            if message:
                payload = {"text": message.text, "type": "message"}
            elif callback:
                payload = {"data": callback.data, "type": "callback"}
            else:
                payload = {}

            event_row = UserEvent(
                user_id=user.id,
                event_type="update",
                payload=payload,
            )
            session.add(event_row)
            await session.commit()

            data["db_user"] = user

        return await handler(event, data)

