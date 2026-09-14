from pydantic_settings import BaseSettings
from typing import Optional

# Configuration class for FastAPI application
# This class is used to store the configuration of the FastAPI application
class Settings(BaseSettings):
    PROJECT_NAME: str = "MedSync CATMS API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8000
    
    # Database configuration (Neon Cloud / PostgreSQL)
    DATABASE_URL: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "neondb"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()