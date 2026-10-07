from fastapi import APIRouter
from app.api.v1.endpoints import (
    health,
    patients,
    doctors,
    appointments,
    users,
    specialties,
    branches,
    staff,
    treatment_categories,
    treatments,
    appointment_treatments,
    invoices,
    payments,
    insurance_providers,
    invoice_items,
)
from app.auth.router import router as auth_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth_router)
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(patients.router)
api_router.include_router(doctors.router)
api_router.include_router(appointments.router)
api_router.include_router(appointments.notes_router)
api_router.include_router(specialties.router)
api_router.include_router(branches.router)
api_router.include_router(staff.router)
api_router.include_router(treatment_categories.router)
api_router.include_router(treatments.router)
api_router.include_router(appointment_treatments.router)
api_router.include_router(invoices.router)
api_router.include_router(payments.router)
api_router.include_router(insurance_providers.router)
api_router.include_router(invoice_items.router)