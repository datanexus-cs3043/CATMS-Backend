from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "MedSync CATMS API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    PORT: int = 8000

    # PostgreSQL Database Configuration
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "medsync"
    DB_USER: str = "neondb_owner"
    DB_PASSWORD: str = ""

    # Connection Pool Settings
    DB_POOL_MIN_SIZE: int = 1
    DB_POOL_MAX_SIZE: int = 10
    DB_POOL_TIMEOUT: float = 30.0

    @property
    def db_conninfo(self) -> str:
        """Returns connection string from DATABASE_URL or constructs one from components."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()