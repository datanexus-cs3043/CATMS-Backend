import asyncpg
from typing import Optional

# Import settings from core/config.py file
from app.core.config import settings

# Global connection pool instance
db_pool: Optional[asyncpg.Pool] = None


async def connect_to_database():
    """Initializes the asyncpg connection pool on FastAPI application startup."""
    global db_pool

    # Check if DATABASE_URL is set or not
    if settings.DATABASE_URL:
        try:
            db_pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            print("[Database] Successfully connected to Database connection pool!")
        except Exception as e:
            print(f"[Database] Warning: Could not connect to database on startup: {e}")
            db_pool = None
    else:
        print("[Database] Warning: DATABASE_URL is not set. Database operations will be unavailable.")


async def close_database_connection():
    """Closes the asyncpg connection pool on FastAPI application shutdown."""
    global db_pool

    if db_pool:
        await db_pool.close()
        print("[Database] Closed database connection pool!")


async def get_db():
    """
    FastAPI Dependency to acquire a database connection from the pool.
    Usage in endpoint:
        @router.get('/example')
        async def example_route(db: asyncpg.Connection = Depends(get_db)):
            records = await db.fetch('SELECT * FROM branches;')
    """
    if db_pool is None:
        raise RuntimeError("[Database] Error: Database connection pool is not initialized. Verify DATABASE_URL.")
    async with db_pool.acquire() as connection:
        yield connection
        # Use `yield` to return the connection to the caller, not like `return`.