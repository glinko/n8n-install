# app/main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy import select, text
from .config import settings
from .middlewares.user_middleware import UserMiddleware
from .routers import start as start_router
from .routers import profile as profile_router
from .routers import admin as admin_router
from .routers import admin_menu as admin_menu_router
from .routers import test_chat as test_chat_router
from .routers import sysopka as sysopka_router
from .routers import claude_cli as claude_cli_router
from .routers import cursor_cli as cursor_cli_router
from .routers import chatgpt_cli as chatgpt_cli_router
from .routers import agent as agent_router
from .models import Base, MenuItem, ChatGPTCLISession, ChatGPTCLIMessage
from .db import engine
from .db import get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Menu structure definition
MENU_STRUCTURE = [
    # Top level items
    {
        "key": "AGENT",
        "label": "Agent",
        "parent_key": None,
        "roles": None,
        "sort_order": 10,
        "is_active": True,
        "action_type": "agent",
        "action_config": None,
    },
    {
        "key": "SYSOPKA",
        "label": "Sysopka",
        "parent_key": None,
        "roles": None,
        "sort_order": 20,
        "is_active": True,
        "action_type": "submenu",
        "action_config": None,
    },
    {
        "key": "PEOPLE",
        "label": "People",
        "parent_key": None,
        "roles": "superadmin",
        "sort_order": 30,
        "is_active": True,
        "action_type": "submenu",
        "action_config": None,
    },
    # Sysopka submenu items
    {
        "key": "SYSOPKA_CHATGPT",
        "label": "ChatgptCLI",
        "parent_key": "SYSOPKA",
        "roles": None,
        "sort_order": 10,
        "is_active": True,
        "action_type": "chatgpt_cli_submenu",
        "action_config": None,
    },
    {
        "key": "SYSOPKA_CLAUDECLI",
        "label": "ClaudeCLI",
        "parent_key": "SYSOPKA",
        "roles": None,
        "sort_order": 20,
        "is_active": True,
        "action_type": "claude_cli_submenu",
        "action_config": None,
    },
    {
        "key": "SYSOPKA_CURSORCLI",
        "label": "CursorCLI",
        "parent_key": "SYSOPKA",
        "roles": None,
        "sort_order": 30,
        "is_active": True,
        "action_type": "cursor_cli_submenu",
        "action_config": None,
    },
    {
        "key": "SYSOPKA_PROXMOX",
        "label": "ProxMox",
        "parent_key": "SYSOPKA",
        "roles": None,
        "sort_order": 40,
        "is_active": True,
        "action_type": "flowise_agentflow",
        "action_config": {"agentflow_id": "88ee84bd-21d1-412b-bff6-81ae33857c1e"},
    },
    {
        "key": "SYSOPKA_HOMENET",
        "label": "HomeNET",
        "parent_key": "SYSOPKA",
        "roles": None,
        "sort_order": 50,
        "is_active": True,
        "action_type": "flowise_agentflow",
        "action_config": {"agentflow_id": "88ee84bd-21d1-412b-bff6-81ae33857c1e"},
    },
    # People submenu items
    {
        "key": "PROFILE",
        "label": "Profile",
        "parent_key": "PEOPLE",
        "roles": "user,superadmin",
        "sort_order": 10,
        "is_active": True,
        "action_type": "profile",
        "action_config": None,
    },
]

async def _seed_menu():
    """Seed menu items from MENU_STRUCTURE. Handles parent-child relationships."""
    async with get_session() as session:
        changed = False
        parent_map = {}  # key -> MenuItem.id
        
        # First pass: create/update all items (we'll set parent_id in second pass)
        for item_def in MENU_STRUCTURE:
            result = await session.execute(
                select(MenuItem).where(MenuItem.key == item_def["key"])
            )
            existing = result.scalar_one_or_none()
            
            # Prepare data without parent_id first
            item_data = {
                k: v for k, v in item_def.items() 
                if k not in ("parent_key",)
            }
            
            if existing:
                dirty = False
                for field in ("label", "roles", "sort_order", "is_active", "action_type", "action_config"):
                    new_value = item_data.get(field)
                    if getattr(existing, field, None) != new_value:
                        setattr(existing, field, new_value)
                        dirty = True
                if dirty:
                    session.add(existing)
                    changed = True
                parent_map[item_def["key"]] = existing.id
            else:
                new_item = MenuItem(**item_data)
                session.add(new_item)
                await session.flush()  # Get the ID
                parent_map[item_def["key"]] = new_item.id
                changed = True
        
        # Second pass: set parent_id relationships
        for item_def in MENU_STRUCTURE:
            if item_def["parent_key"]:
                result = await session.execute(
                    select(MenuItem).where(MenuItem.key == item_def["key"])
                )
                item = result.scalar_one_or_none()
                if item and item_def["parent_key"] in parent_map:
                    parent_id = parent_map[item_def["parent_key"]]
                    if item.parent_id != parent_id:
                        item.parent_id = parent_id
                        session.add(item)
                        changed = True
        
        # Deactivate legacy items that are no longer in the structure
        legacy_keys = ["FAMILY_PANEL", "TEST_CHAT", "CHATGPT"]
        for legacy_key in legacy_keys:
            if legacy_key not in [item["key"] for item in MENU_STRUCTURE]:
                result = await session.execute(
                    select(MenuItem).where(MenuItem.key == legacy_key)
                )
                legacy_item = result.scalar_one_or_none()
                if legacy_item and legacy_item.is_active:
                    legacy_item.is_active = False
                    session.add(legacy_item)
                    changed = True
        
        if changed:
            await session.commit()
            logging.info("Menu items synced.")

async def on_startup():
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        # Add new columns if they don't exist (migration)
        await conn.execute(
            text("""
            DO $$ 
            BEGIN
                -- Add action_type column if it doesn't exist
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='menu_items' AND column_name='action_type'
                ) THEN
                    ALTER TABLE menu_items ADD COLUMN action_type VARCHAR(64);
                END IF;
                
                -- Add action_config column if it doesn't exist
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='menu_items' AND column_name='action_config'
                ) THEN
                    ALTER TABLE menu_items ADD COLUMN action_config JSONB;
                END IF;
                
                -- Add unique constraint for claude_cli_sessions if table exists
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='claude_cli_sessions') THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname='claude_cli_sessions_user_session_unique'
                    ) THEN
                        ALTER TABLE claude_cli_sessions ADD CONSTRAINT claude_cli_sessions_user_session_unique 
                        UNIQUE (user_id, session_name);
                    END IF;
                    
                    -- Add uuid column if it doesn't exist
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='claude_cli_sessions' AND column_name='uuid'
                    ) THEN
                        ALTER TABLE claude_cli_sessions ADD COLUMN uuid VARCHAR(128);
                        CREATE INDEX IF NOT EXISTS idx_claude_cli_sessions_uuid ON claude_cli_sessions(uuid);
                    END IF;
                END IF;
                
                -- Update claude_cli_messages.session_id to allow NULL and add ondelete SET NULL
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='claude_cli_messages') THEN
                    -- Make session_id nullable if not already
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='claude_cli_messages' 
                        AND column_name='session_id' 
                        AND is_nullable='NO'
                    ) THEN
                        ALTER TABLE claude_cli_messages ALTER COLUMN session_id DROP NOT NULL;
                    END IF;
                END IF;
                
                -- Add unique constraint for cursor_cli_sessions if table exists
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='cursor_cli_sessions') THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname='cursor_cli_sessions_user_session_unique'
                    ) THEN
                        ALTER TABLE cursor_cli_sessions ADD CONSTRAINT cursor_cli_sessions_user_session_unique 
                        UNIQUE (user_id, session_name);
                    END IF;
                    
                    -- Add uuid column if it doesn't exist
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='cursor_cli_sessions' AND column_name='uuid'
                    ) THEN
                        ALTER TABLE cursor_cli_sessions ADD COLUMN uuid VARCHAR(128);
                        CREATE INDEX IF NOT EXISTS idx_cursor_cli_sessions_uuid ON cursor_cli_sessions(uuid);
                    END IF;
                END IF;
                
                -- Update cursor_cli_messages.session_id to allow NULL and add ondelete SET NULL
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='cursor_cli_messages') THEN
                    -- Make session_id nullable if not already
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='cursor_cli_messages' 
                        AND column_name='session_id' 
                        AND is_nullable='NO'
                    ) THEN
                        ALTER TABLE cursor_cli_messages ALTER COLUMN session_id DROP NOT NULL;
                    END IF;
                END IF;
            END $$;
            """)
        )
    logging.info("DB synced and migrated.")
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

    # ClaudeCLI, CursorCLI and ChatGPT CLI routers must be registered FIRST to handle state-based handlers
    # (state handlers have higher priority, but router order matters for message propagation)
    dp.include_router(claude_cli_router.router)
    dp.include_router(cursor_cli_router.router)
    dp.include_router(chatgpt_cli_router.router)
    dp.include_router(agent_router.router)
    # Start router handles menu buttons dynamically - registered after to allow CLI state handlers first
    dp.include_router(start_router.router)
    # Then include other routers
    dp.include_router(test_chat_router.router)
    dp.include_router(sysopka_router.router)
    dp.include_router(profile_router.router)
    dp.include_router(admin_router.router)
    dp.include_router(admin_menu_router.router)

    logging.info("Bot started polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
