# app/main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy import select
from .config import settings
from .middlewares.user_middleware import UserMiddleware
from .routers import start as start_router
from .routers import profile as profile_router
from .routers import admin as admin_router
from .routers import admin_menu as admin_menu_router
from .models import Base, MenuItem
from .db import engine
from .db import get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

async def _seed_menu():
    async with get_session() as session:
        result = await session.execute(select(MenuItem))
        existing = result.scalars().first()
        if existing:
            return

        profile = MenuItem(
            key="PROFILE",
            label="👤 Мой профиль",
            roles="user,superadmin",
            sort_order=10,
            is_active=True,
        )
        family_panel = MenuItem(
            key="FAMILY_PANEL",
            label="🏡 Семейная панель",
            roles="superadmin",
            sort_order=20,
            is_active=True,
        )
        session.add_all([profile, family_panel])
        await session.commit()
        logging.info("Seeded default menu items.")

async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("DB synced.")
    await _seed_menu()

async def main():
    await on_startup()

    bot = Bot(token=settings.telegram_bot_token)
    redis = Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db,
        password=settings.redis.password,
    )
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    dp.update.middleware(UserMiddleware())

    dp.include_router(start_router.router)
    dp.include_router(profile_router.router)
    dp.include_router(admin_router.router)
    dp.include_router(admin_menu_router.router)

    logging.info("Bot started polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())

