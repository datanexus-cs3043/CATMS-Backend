from typing import Optional, List
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

    # Authentication & JWT Security Settings
    JWT_SECRET_KEY: str = "medsync_super_secret_jwt_key_cs3043_university_database_project_2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # HttpOnly Cookie Settings
    COOKIE_NAME: str = "medsync_access_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    # CSRF Protection Settings
    CSRF_SECRET_KEY: str = "medsync_csrf_secret_key_protection_2026_catms"

    # CORS Frontend Origins (comma-separated or string)
    FRONTEND_URLS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    @property
    def db_conninfo(self) -> str:
        """Returns connection string from DATABASE_URL or constructs one from components."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def cors_origins(self) -> List[str]:
        """Parses comma-separated FRONTEND_URLS into a list of allowed origins."""
        return [url.strip() for url in self.FRONTEND_URLS.split(",") if url.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()