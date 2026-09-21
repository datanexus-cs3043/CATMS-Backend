import sys
import asyncio

# On Windows, psycopg async requires WindowsSelectorEventLoopPolicy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from psycopg import AsyncConnection

from app.core.config import settings
from app.core.database import connect_to_database, close_database_connection, get_db
from app.api.v1.api import api_router
from app.schemas.health import HealthResponse

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("medsync.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application lifecycle: connects psycopg3 pool on startup, closes it on shutdown."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    await connect_to_database()
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")
    await close_database_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="MedSync - Clinic Appointment and Treatment Management System (CATMS) API",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration for Frontend with credentials (HttpOnly Cookie support)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router under /api (e.g., /api/health, /api/auth/login, etc.)
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Root"])
def root():
    """Root metadata endpoint."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_check": f"{settings.API_PREFIX}/health",
    }


@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def root_health(conn: AsyncConnection = Depends(get_db)):
    """Convenience health endpoint at root level."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT current_database() AS db_name, version() AS db_version, NOW()::text AS server_time;")
        db_info = await cur.fetchone()
        return HealthResponse(
            status="healthy",
            database="connected",
            database_name=db_info["db_name"] if db_info else None,
            database_version=db_info["db_version"] if db_info else None,
            server_time=db_info["server_time"] if db_info else None,
        )
