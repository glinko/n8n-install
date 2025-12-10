# app/config.py
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os

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

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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
    def superadmin_ids(self) -> List[int]:
        if not self.superadmin_ids_raw:
            return []
        return [int(x.strip()) for x in self.superadmin_ids_raw.split(",") if x.strip()]

settings = Settings()

