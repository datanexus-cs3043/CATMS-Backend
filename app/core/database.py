import sys
import asyncio
import logging
from typing import AsyncGenerator, Optional, Any, List, Dict

# On Windows, psycopg async requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from psycopg_pool import AsyncConnectionPool
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.config import settings

logger = logging.getLogger("medsync.database")

# Global async connection pool instance for psycopg3
db_pool: Optional[AsyncConnectionPool] = None


async def connect_to_database() -> None:
    """Initializes the psycopg3 AsyncConnectionPool on FastAPI startup."""
    global db_pool
    if db_pool is not None:
        return

    conninfo = settings.db_conninfo
    if not conninfo:
        logger.warning("[Database] No database connection string provided. Database features will be disabled.")
        return

    try:
        logger.info("[Database] Initializing PostgreSQL psycopg3 connection pool...")
        db_pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            timeout=settings.DB_POOL_TIMEOUT,
            kwargs={
                "row_factory": dict_row,
                "autocommit": True,
            },
            open=False,
        )
        await db_pool.open()
        
        # Test the connection pool immediately
        async with db_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT current_database(), version();")
                result = await cur.fetchone()
                db_name = result["current_database"] if result else "unknown"
                logger.info(f"[Database] Successfully connected to PostgreSQL database '{db_name}'!")
    except Exception as e:
        logger.error(f"[Database] Failed to connect to PostgreSQL database: {e}")
        db_pool = None
        raise e


async def close_database_connection() -> None:
    """Closes the psycopg3 AsyncConnectionPool on FastAPI shutdown."""
    global db_pool
    if db_pool:
        logger.info("[Database] Closing PostgreSQL psycopg3 connection pool...")
        await db_pool.close()
        db_pool = None
        logger.info("[Database] Connection pool closed.")


async def get_db() -> AsyncGenerator[AsyncConnection, None]:
    """
    FastAPI dependency that yields an active psycopg3 AsyncConnection from the pool.
    Usage in route endpoints:
        @router.get('/items')
        async def read_items(conn: AsyncConnection = Depends(get_db)):
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM treatment;")
                return await cur.fetchall()
    """
    global db_pool
    if db_pool is None:
        await connect_to_database()

    if db_pool is None:
        raise RuntimeError("Database connection pool is not initialized. Check your database configuration.")

    async with db_pool.connection() as connection:
        yield connection


async def fetch_one(query: str, params: Optional[tuple | dict] = None) -> Optional[Dict[str, Any]]:
    """Helper utility to execute a direct SQL query and fetch a single record."""
    global db_pool
    if db_pool is None:
        await connect_to_database()
    if db_pool is None:
        raise RuntimeError("Database connection pool is not initialized.")
    async with db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()


async def fetch_all(query: str, params: Optional[tuple | dict] = None) -> List[Dict[str, Any]]:
    """Helper utility to execute a direct SQL query and fetch all matching records."""
    global db_pool
    if db_pool is None:
        await connect_to_database()
    if db_pool is None:
        raise RuntimeError("Database connection pool is not initialized.")
    async with db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()