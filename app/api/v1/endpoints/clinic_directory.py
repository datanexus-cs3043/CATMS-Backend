"""Public brochure data only; account, patient and staff contacts stay private."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from psycopg import AsyncConnection

from app.core.database import get_db

router = APIRouter(prefix="/public", tags=["Clinic directory"])


class PublicBranch(BaseModel):
    branch_id: int
    branch_name: str
    location: str
    contact_details: str | None = None


class PublicSpecialty(BaseModel):
    specialty_id: int
    specialty_name: str
    description: str | None = None


class ClinicDirectory(BaseModel):
    branches: list[PublicBranch]
    specialties: list[PublicSpecialty]
    doctor_count: int
    service_count: int


@router.get("/clinic-directory", response_model=ClinicDirectory)
async def clinic_directory(conn: AsyncConnection = Depends(get_db)):
    # One statement supplies a consistent directory snapshot without N+1 reads.
    # Explicit projections must not expose manager IDs, licences or staff emails.
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT
                COALESCE((SELECT jsonb_agg(x ORDER BY x.branch_id)
                    FROM (SELECT branch_id, branch_name, location, contact_details
                          FROM branch) x), '[]'::jsonb) AS branches,
                COALESCE((SELECT jsonb_agg(x ORDER BY x.specialty_name)
                    FROM (SELECT specialty_id, specialty_name, description
                          FROM specialty) x), '[]'::jsonb) AS specialties,
                (SELECT count(*) FROM doctor) AS doctor_count,
                (SELECT count(*) FROM treatment) AS service_count;
        """)
        return ClinicDirectory(**await cur.fetchone())
