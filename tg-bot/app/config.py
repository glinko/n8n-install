# app/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
from pathlib import Path

class DbSettings(BaseModel):
    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

class RedisSettings(BaseModel):
    host: str
    port: int
    db: int
    password: str | None = None

def _get_env_file_path() -> str | None:
    """Get path to .env file. Prefers root project .env if available."""
    # Try explicit path from environment variable
    explicit_path = os.getenv("ENV_FILE_PATH")
    if explicit_path and Path(explicit_path).exists():
        return explicit_path
    
    # Try root project .env (for local development)
    root_env = Path("/home/user/n8n-install/.env")
    if root_env.exists():
        return str(root_env)
    
    # Try .env in current directory (fallback)
    current_env = Path(".env")
    if current_env.exists():
        return str(current_env)
    
    # Return None if no .env found (will rely on environment variables)
    return None

env_file_path = _get_env_file_path()
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_file_path, 
        env_file_encoding="utf-8",
        env_ignore_empty=True
    )

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    superadmin_ids_raw: str = os.getenv("SUPERADMIN_IDS", "")

    db_host: str = os.getenv("DB_HOST", "postgres")
    db_port: int = int(os.getenv("DB_PORT", 5432))
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "postgres")
    db_name: str = os.getenv("DB_NAME", "postgres")

    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", 6379))
    redis_db: int = int(os.getenv("REDIS_DB", 0))
    redis_password: str | None = os.getenv("REDIS_PASSWORD") or None

    flowise_base_url: str = os.getenv("FLOWISE_BASE_URL", "https://flowise.rootnode.cv")
    flowise_api_key: str = os.getenv("FLOWISE_API_KEY", "")
    testchat_chatflow_id: str = os.getenv("TESTCHAT_CHATFLOW_ID", "")

    # Sysopka agentflows for different specialties
    sysopka_claudecli_id: str = os.getenv("SYSOPKA_CLAUDECLI_ID", "")
    sysopka_proxmox_id: str = os.getenv("SYSOPKA_PROXMOX_ID", "")
    sysopka_homenet_id: str = os.getenv("SYSOPKA_HOMENET_ID", "")
    sysopka_chatbot_id: str = os.getenv("SYSOPKA_CHATBOT_ID", "")

    @property
    def db(self) -> DbSettings:
        return DbSettings(
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_password,
            name=self.db_name,
        )

    @property
    def redis(self) -> RedisSettings:
        return RedisSettings(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
        )

    @property
    def flowise_base(self) -> str:
        return self.flowise_base_url.rstrip("/")

    @property
    def has_flowise_testchat(self) -> bool:
        return bool(self.flowise_api_key and self.testchat_chatflow_id)

    @property
    def has_flowise_sysopka(self) -> bool:
        return bool(self.flowise_api_key and any([
            self.sysopka_claudecli_id,
            self.sysopka_proxmox_id,
            self.sysopka_homenet_id,
            self.sysopka_chatbot_id
        ]))

    def get_sysopka_id(self, sysopka_type: str) -> str:
        """Get agentflow ID for specific Sysopka type"""
        mapping = {
            "claudecli": self.sysopka_claudecli_id,
            "proxmox": self.sysopka_proxmox_id,
            "homenet": self.sysopka_homenet_id,
            "chatbot": self.sysopka_chatbot_id,
        }
        return mapping.get(sysopka_type, "")

    @property
    def superadmin_ids(self) -> List[int]:
        if not self.superadmin_ids_raw:
            return []
        return [int(x.strip()) for x in self.superadmin_ids_raw.split(",") if x.strip()]

settings = Settings()
