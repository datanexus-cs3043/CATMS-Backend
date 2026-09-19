from fastapi import APIRouter
from app.api.v1.endpoints import health, patients, doctors, appointments

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(patients.router)
api_router.include_router(doctors.router)
api_router.include_router(appointments.router)

