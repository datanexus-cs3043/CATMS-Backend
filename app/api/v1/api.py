from fastapi import APIRouter
from app.api.v1.endpoints import health
from app.auth.router import router as auth_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth_router)
