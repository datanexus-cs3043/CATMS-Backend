from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.v1.endpoints._guards import STAFF_ROLES, check_branch_scope, database_mutation
from app.api.v1.endpoints.patients import _check_patient_access
from app.auth.dependencies import get_current_user, require_csrf, require_role
from app.auth.schemas import JWTPayload
from app.core.database import get_db
from app.schemas.insurance_coverage import (
    InsuranceCoverageCreate,
    InsuranceCoverageResponse,
    InsuranceCoverageUpdate,
)

router = APIRouter(prefix="/insurance/coverage", tags=["Insurance Coverage"])
COVERAGE_WRITE_ROLES = ("admin", "branch_manager", "receptionist_cashier")


async def _get_coverage(cur, coverage_id: int, *, lock: bool = True) -> dict:
    await cur.execute(
        """SELECT c.*, t.treatment_name, p.patient_id, pt.branch_id
           FROM insurance_coverage c
           JOIN insurance_policy p ON p.policy_id = c.policy_id
           JOIN patient pt ON pt.patient_id = p.patient_id
           LEFT JOIN treatment t ON t.treatment_id = c.treatment_id
           WHERE c.coverage_id = %s""" + (" FOR UPDATE OF c" if lock else "") + ";",
        (coverage_id,),
    )
    coverage = await cur.fetchone()
    if not coverage:
        raise HTTPException(404, f"Insurance coverage {coverage_id} not found")
    return coverage


def _authorize_coverage(coverage: dict, current_user: JWTPayload, *, write: bool = False) -> None:
    if current_user.user_type == "patient":
        if current_user.patient_id != coverage["patient_id"]:
            raise HTTPException(403, "You are not authorized to access this insurance coverage.")
        if write:
            raise HTTPException(403, "Patients cannot modify insurance coverage.")
        return
    if current_user.role.lower() not in STAFF_ROLES:
        raise HTTPException(403, "Staff credentials required for this resource.")
    check_branch_scope(coverage["branch_id"], current_user)


async def _lock_policy(cur, policy_id: int) -> dict:
    # Claims take FOR SHARE on the parent policy before reading coverage. Every
    # coverage mutation must take this exclusive parent lock first, including
    # inserts, so new rules cannot appear halfway through eligibility checking.
    await cur.execute(
        """SELECT p.policy_id, pt.patient_id, pt.branch_id
           FROM insurance_policy p
           JOIN patient pt ON pt.patient_id = p.patient_id
           WHERE p.policy_id = %s FOR UPDATE OF p;""",
        (policy_id,),
    )
    policy = await cur.fetchone()
    if not policy:
        raise HTTPException(422, f"Insurance policy {policy_id} not found")
    return policy


async def _validate_references(cur, policy_id: int, treatment_id: int) -> dict:
    policy = await _lock_policy(cur, policy_id)
    await cur.execute("SELECT treatment_id FROM treatment WHERE treatment_id = %s;", (treatment_id,))
    if not await cur.fetchone():
        raise HTTPException(422, f"Treatment {treatment_id} not found")
    return policy


@router.get("", response_model=List[InsuranceCoverageResponse])
async def list_insurance_coverage(
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        query = """SELECT c.*, t.treatment_name, p.patient_id, pt.branch_id
                   FROM insurance_coverage c
                   JOIN insurance_policy p ON p.policy_id = c.policy_id
                   JOIN patient pt ON pt.patient_id = p.patient_id
                   LEFT JOIN treatment t ON t.treatment_id = c.treatment_id"""
        params = []
        if current_user.user_type == "patient":
            if current_user.role.lower() != "patient" or current_user.patient_id is None:
                raise HTTPException(403, "A linked patient profile is required.")
            query += " WHERE p.patient_id = %s"
            params.append(current_user.patient_id)
        else:
            # Coverage reads follow shared patient access, independently of write scope.
            check_branch_scope(current_user.branch_id, current_user)
            if current_user.role.lower() == "doctor":
                if current_user.doctor_id is None:
                    raise HTTPException(403, "A linked doctor profile is required.")
                query += " WHERE EXISTS (SELECT 1 FROM appointment a WHERE a.patient_id = p.patient_id AND a.doctor_id = %s AND a.branch_id = %s)"
                params.extend([current_user.doctor_id, current_user.branch_id])
        query += " ORDER BY c.coverage_id ASC;"
        await cur.execute(query, tuple(params))
        return [InsuranceCoverageResponse(**row) for row in await cur.fetchall()]


@router.get("/{coverage_id}", response_model=InsuranceCoverageResponse)
async def get_insurance_coverage(
    coverage_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(get_current_user),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        coverage = await _get_coverage(cur, coverage_id, lock=False)
    await _check_patient_access(conn, coverage["patient_id"], current_user)
    return InsuranceCoverageResponse(**coverage)


@router.post(
    "",
    response_model=InsuranceCoverageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_insurance_coverage(
    payload: InsuranceCoverageCreate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*COVERAGE_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        policy = await _validate_references(cur, payload.policy_id, payload.treatment_id)
        check_branch_scope(policy["branch_id"], current_user)
        await cur.execute(
            """INSERT INTO insurance_coverage
               (policy_id, treatment_id, coverage_percentage, maximum_amount)
               VALUES (%s, %s, %s, %s) RETURNING coverage_id;""",
            (payload.policy_id, payload.treatment_id,
             payload.coverage_percentage, payload.maximum_amount),
        )
        coverage_id = (await cur.fetchone())["coverage_id"]
        coverage = await _get_coverage(cur, coverage_id)
    return InsuranceCoverageResponse(**coverage)


@router.put(
    "/{coverage_id}",
    response_model=InsuranceCoverageResponse,
    dependencies=[Depends(require_csrf)],
)
async def update_insurance_coverage(
    coverage_id: int,
    payload: InsuranceCoverageUpdate,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*COVERAGE_WRITE_ROLES)),
):
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No update fields provided")
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        coverage = await _get_coverage(cur, coverage_id, lock=False)
        _authorize_coverage(coverage, current_user, write=True)
        policy_id = update_data.get("policy_id", coverage["policy_id"])
        original_policy_id = coverage["policy_id"]
        # Lock both parents in stable order before the child if a rule is moved.
        for locked_policy_id in sorted({original_policy_id, policy_id}):
            policy = await _lock_policy(cur, locked_policy_id)
            _authorize_coverage(policy, current_user, write=True)
        coverage = await _get_coverage(cur, coverage_id)
        _authorize_coverage(coverage, current_user, write=True)
        if coverage["policy_id"] != original_policy_id:
            raise HTTPException(409, "The coverage policy changed. Refresh before editing it.")
        treatment_id = update_data.get("treatment_id", coverage["treatment_id"])
        policy = await _validate_references(cur, policy_id, treatment_id)
        check_branch_scope(policy["branch_id"], current_user)
        clauses = [f"{key} = %s" for key in update_data]
        values = list(update_data.values()) + [coverage_id]
        await cur.execute(
            f"UPDATE insurance_coverage SET {', '.join(clauses)} "
            "WHERE coverage_id = %s;",
            tuple(values),
        )
        coverage = await _get_coverage(cur, coverage_id)
    return InsuranceCoverageResponse(**coverage)


@router.delete(
    "/{coverage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_insurance_coverage(
    coverage_id: int,
    conn: AsyncConnection = Depends(get_db),
    current_user: JWTPayload = Depends(require_role(*COVERAGE_WRITE_ROLES)),
):
    async with database_mutation(conn), conn.cursor(row_factory=dict_row) as cur:
        coverage = await _get_coverage(cur, coverage_id, lock=False)
        _authorize_coverage(coverage, current_user, write=True)
        policy = await _lock_policy(cur, coverage["policy_id"])
        _authorize_coverage(policy, current_user, write=True)
        coverage = await _get_coverage(cur, coverage_id)
        _authorize_coverage(coverage, current_user, write=True)
        if coverage["policy_id"] != policy["policy_id"]:
            raise HTTPException(409, "The coverage policy changed. Refresh before deleting it.")
        await cur.execute("DELETE FROM insurance_coverage WHERE coverage_id = %s;", (coverage_id,))
    return None
