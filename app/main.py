from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import asyncpg

# Import the settings, this will give us the project name and version, and other settings
from app.core.config import settings

# Import the database connection functions, those will make the connection
from app.core.database import connect_to_database, close_database_connection, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code executed before the application starts taking requests
    await connect_to_database()
    yield
    # Code executed when the application is shutting down
    await close_database_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Clinic Appointment and Treatment Management System API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": f"{settings.PROJECT_NAME} is active",
        "version": settings.VERSION,
        "docs_url": "/docs"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/health/db")
async def health_db(db: asyncpg.Connection = Depends(get_db)):
    """Verifies live database connectivity by running a basic SELECT query."""
    result = await db.fetchval("SELECT current_database();")
    return {"database_status": "connected", "connected_database": result}
