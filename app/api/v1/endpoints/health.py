from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
import logging

from app.core.database import get_db
from app.schemas.health import HealthResponse

logger = logging.getLogger("medsync.api.health")
router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check and database connectivity verification",
    description="Verifies the operational status of the FastAPI backend and confirms live connectivity with the PostgreSQL database using psycopg3.",
)
async def check_health(conn: AsyncConnection = Depends(get_db)):
    try:
        async with conn.cursor() as cur:
            # Check basic connection, database name, version, and server time
            await cur.execute("""
                SELECT 
                    current_database() AS db_name,
                    version() AS db_version,
                    NOW()::text AS server_time;
            """)
            db_info = await cur.fetchone()

            # Query count of base tables in the public schema
            await cur.execute("""
                SELECT COUNT(*) AS table_count 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
            """)
            table_info = await cur.fetchone()
            table_count = table_info["table_count"] if table_info else 0

            return HealthResponse(
                status="healthy",
                database="connected",
                database_name=db_info["db_name"] if db_info else None,
                database_version=db_info["db_version"] if db_info else None,
                server_time=db_info["server_time"] if db_info else None,
                detected_tables_count=table_count,
            )
    except Exception as e:
        logger.error(f"Health check database query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
            },
        )

