"""Fail-closed guards used by the endpoints introduced in PR #9."""

from contextlib import asynccontextmanager

from fastapi import HTTPException
from psycopg.errors import CheckViolation, ForeignKeyViolation, NotNullViolation, UniqueViolation

from app.auth.schemas import JWTPayload


STAFF_ROLES = ("admin", "branch_manager", "doctor", "receptionist_cashier")


def check_branch_scope(branch_id: int, user: JWTPayload) -> None:
    if user.user_type != "staff" or user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    if user.role.lower() != "admin" and (user.branch_id is None or user.branch_id != branch_id):
        raise HTTPException(403, "Access is restricted to your assigned branch.")


@asynccontextmanager
async def database_mutation(conn):
    """Rollback the whole operation before translating known constraint failures."""
    try:
        async with conn.transaction():
            yield
    except ForeignKeyViolation as exc:
        raise HTTPException(409, "The operation conflicts with related records.") from exc
    except UniqueViolation as exc:
        raise HTTPException(409, "A record with these unique values already exists.") from exc
    except (NotNullViolation, CheckViolation) as exc:
        raise HTTPException(422, "The values violate a database constraint.") from exc
