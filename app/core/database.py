import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Any, List, Dict

# On Windows, psycopg async requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from psycopg_pool import AsyncConnectionPool, PoolClosed, PoolTimeout, TooManyRequests
from psycopg import AsyncConnection, OperationalError
from psycopg.rows import dict_row
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger("medsync.database")

# Global async connection pool instance for psycopg3
db_pool: Optional[AsyncConnectionPool] = None
_initialization_task: Optional[asyncio.Task[None]] = None


async def _configure_clinic_timezone(connection: AsyncConnection) -> None:
    """CURRENT_DATE and local timestamps use the clinic's day, not host UTC."""
    await connection.execute("SET TIME ZONE 'Asia/Colombo';")


async def connect_to_database() -> None:
    """Share one pool initialization between startup and concurrent requests."""
    global _initialization_task
    if db_pool is not None:
        return
    # No await between checking and publishing the task: one task per event loop.
    if _initialization_task is None:
        _initialization_task = asyncio.create_task(_initialize_database_pool())
    task = _initialization_task
    try:
        # A cancelled request must not cancel initialization for other requests.
        await asyncio.shield(task)
    finally:
        if task.done() and _initialization_task is task:
            _initialization_task = None


async def _initialize_database_pool() -> None:
    global db_pool

    conninfo = settings.db_conninfo
    if not conninfo:
        logger.warning("[Database] No database connection string provided. Database features will be disabled.")
        return

    pool: Optional[AsyncConnectionPool] = None
    try:
        logger.info("[Database] Initializing PostgreSQL psycopg3 connection pool...")
        pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            timeout=settings.DB_POOL_TIMEOUT,
            configure=_configure_clinic_timezone,
            kwargs={
                "row_factory": dict_row,
                "autocommit": True,
            },
            open=False,
        )
        await pool.open()

        # Test the connection pool immediately
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT current_database(), version();")
                result = await cur.fetchone()
                db_name = result["current_database"] if result else "unknown"
                logger.info(f"[Database] Successfully connected to PostgreSQL database '{db_name}'!")
        db_pool = pool
    except Exception:
        logger.exception("[Database] Failed to connect to PostgreSQL database")
        raise
    finally:
        # Also clean up when startup is cancelled before the pool is published.
        if pool is not None and db_pool is not pool:
            try:
                await pool.close()
            except Exception:
                logger.exception("[Database] Failed to close the unsuccessful connection pool")


async def close_database_connection() -> None:
    """Closes the psycopg3 AsyncConnectionPool on FastAPI shutdown."""
    global db_pool, _initialization_task
    task = _initialization_task
    if task is not None:
        try:
            await asyncio.shield(task)
        except Exception:
            # Initialization already logs the failure and closes its failed pool.
            pass
        finally:
            if task.done() and _initialization_task is task:
                _initialization_task = None
    pool = db_pool
    db_pool = None
    if pool is not None:
        logger.info("[Database] Closing PostgreSQL psycopg3 connection pool...")
        await pool.close()
        logger.info("[Database] Connection pool closed.")


@asynccontextmanager
async def _database_connection():
    if db_pool is None:
        try:
            await connect_to_database()
        except OperationalError as exc:
            raise HTTPException(503, "Database service is unavailable.") from exc
    pool = db_pool
    if pool is None:
        raise HTTPException(503, "Database service is unavailable.")
    try:
        async with pool.connection() as connection:
            yield connection
    except (PoolTimeout, PoolClosed, TooManyRequests) as exc:
        logger.warning("[Database] Connection acquisition unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, "Database service is unavailable.") from exc


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
    async with _database_connection() as connection:
        yield connection


async def fetch_one(query: str, params: Optional[tuple | dict] = None) -> Optional[Dict[str, Any]]:
    """Helper utility to execute a direct SQL query and fetch a single record."""
    async with _database_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()


async def fetch_all(query: str, params: Optional[tuple | dict] = None) -> List[Dict[str, Any]]:
    """Helper utility to execute a direct SQL query and fetch all matching records."""
    async with _database_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()
