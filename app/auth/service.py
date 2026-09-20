import logging
from typing import Optional, Dict, Any
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.auth.security import verify_password
from app.auth.schemas import AuthUser, UserType, UserRole

logger = logging.getLogger("medsync.auth.service")


def normalize_role(role_raw: Optional[str], staff_type_raw: Optional[str], is_doctor: bool) -> str:
    """Normalizes various database role strings into one of the 5 canonical MedSync roles."""
    role_str = (role_raw or "").strip().lower()
    staff_str = (staff_type_raw or "").strip().lower()

    if "admin" in role_str or "admin" in staff_str:
        return UserRole.ADMIN.value
    if "manager" in role_str or "manager" in staff_str:
        return UserRole.BRANCH_MANAGER.value
    if is_doctor or "doctor" in role_str or "doctor" in staff_str:
        return UserRole.DOCTOR.value
    if "reception" in role_str or "cashier" in role_str or "reception" in staff_str or "cashier" in staff_str:
        return UserRole.RECEPTIONIST_CASHIER.value
    
    return UserRole.PATIENT.value


async def authenticate_user(
    conn: AsyncConnection,
    username: str,
    plain_password: str
) -> Optional[AuthUser]:
    """
    Authenticates a user via direct SQL:
    1. Fetches the user record from the "user" table.
    2. Verifies the password hash.
    3. Determines if the account belongs to a Staff or a Patient.
    4. Records a login audit event into users_logins.
    5. Returns safe AuthUser details (or None if invalid).
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        # 1. Fetch user by username (case-insensitive search)
        await cur.execute(
            """
            SELECT user_id, first_name, last_name, contact_details, email, username, password
            FROM "user"
            WHERE LOWER(username) = LOWER(%s);
            """,
            (username.strip(),)
        )
        user_row = await cur.fetchone()

        if not user_row:
            logger.info(f"Authentication failed: User '{username}' not found.")
            return None

        # 2. Verify password hash
        stored_hash = user_row.get("password") or ""
        if not verify_password(plain_password, stored_hash):
            logger.info(f"Authentication failed: Incorrect password for user '{username}'.")
            return None

        user_id = user_row["user_id"]
        user_name = user_row["username"]
        email = user_row.get("email")
        contact_details = user_row.get("contact_details")

        # 3. Check if user is associated with a Staff record
        await cur.execute(
            """
            SELECT 
                s.staff_id, 
                s.branch_id, 
                s.staff_type, 
                s.role,
                d.doctor_id
            FROM staff s
            LEFT JOIN doctor d ON d.staff_id = s.staff_id
            LEFT JOIN users_logins ul ON ul.users_logins_id = s.users_logins_id
            WHERE ul.user_id = %s OR (s.email IS NOT NULL AND LOWER(s.email) = LOWER(%s))
            LIMIT 1;
            """,
            (user_id, email or "")
        )
        staff_row = await cur.fetchone()

        if staff_row:
            is_doctor = staff_row["doctor_id"] is not None
            resolved_role = normalize_role(staff_row["role"], staff_row["staff_type"], is_doctor)
            
            auth_user = AuthUser(
                user_id=user_id,
                user_type=UserType.STAFF.value,
                role=resolved_role,
                username=user_name,
                email=email,
                first_name=user_row.get("first_name"),
                last_name=user_row.get("last_name"),
                staff_id=staff_row["staff_id"],
                doctor_id=staff_row.get("doctor_id"),
                branch_id=staff_row.get("branch_id"),
            )
        else:
            # 4. Check if user is associated with a Patient record
            patient_row = None
            if email or contact_details:
                await cur.execute(
                    """
                    SELECT patient_id, branch_id
                    FROM patient
                    WHERE (email IS NOT NULL AND LOWER(email) = LOWER(%s))
                       OR (contact_details IS NOT NULL AND contact_details = %s)
                    LIMIT 1;
                    """,
                    (email or "", contact_details or "")
                )
                patient_row = await cur.fetchone()

            if patient_row:
                auth_user = AuthUser(
                    user_id=user_id,
                    user_type=UserType.PATIENT.value,
                    role=UserRole.PATIENT.value,
                    username=user_name,
                    email=email,
                    first_name=user_row.get("first_name"),
                    last_name=user_row.get("last_name"),
                    patient_id=patient_row["patient_id"],
                    branch_id=patient_row.get("branch_id"),
                )
            else:
                # Default fallback for administrative or patient user accounts not linked to secondary table
                fallback_role = UserRole.ADMIN.value if "admin" in user_name.lower() else UserRole.PATIENT.value
                fallback_type = UserType.STAFF.value if fallback_role == UserRole.ADMIN.value else UserType.PATIENT.value
                auth_user = AuthUser(
                    user_id=user_id,
                    user_type=fallback_type,
                    role=fallback_role,
                    username=user_name,
                    email=email,
                    first_name=user_row.get("first_name"),
                    last_name=user_row.get("last_name"),
                )

        # 5. Record login audit in users_logins table
        try:
            await cur.execute(
                """
                INSERT INTO users_logins (user_id, login_time, user_name)
                VALUES (%s, NOW(), %s)
                RETURNING users_logins_id;
                """,
                (user_id, user_name)
            )
        except Exception as audit_err:
            logger.warning(f"Could not record users_logins audit entry: {audit_err}")

        return auth_user


async def get_user_by_id(conn: AsyncConnection, user_id: int) -> Optional[AuthUser]:
    """Fetches user details and associated role/staff/patient ID by user_id."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT user_id, first_name, last_name, contact_details, email, username
            FROM "user"
            WHERE user_id = %s;
            """,
            (user_id,)
        )
        user_row = await cur.fetchone()
        if not user_row:
            return None

        email = user_row.get("email")
        contact_details = user_row.get("contact_details")

        # Check Staff
        await cur.execute(
            """
            SELECT 
                s.staff_id, 
                s.branch_id, 
                s.staff_type, 
                s.role,
                d.doctor_id
            FROM staff s
            LEFT JOIN doctor d ON d.staff_id = s.staff_id
            LEFT JOIN users_logins ul ON ul.users_logins_id = s.users_logins_id
            WHERE ul.user_id = %s OR (s.email IS NOT NULL AND LOWER(s.email) = LOWER(%s))
            LIMIT 1;
            """,
            (user_id, email or "")
        )
        staff_row = await cur.fetchone()

        if staff_row:
            is_doctor = staff_row["doctor_id"] is not None
            resolved_role = normalize_role(staff_row["role"], staff_row["staff_type"], is_doctor)
            return AuthUser(
                user_id=user_id,
                user_type=UserType.STAFF.value,
                role=resolved_role,
                username=user_row.get("username"),
                email=email,
                first_name=user_row.get("first_name"),
                last_name=user_row.get("last_name"),
                staff_id=staff_row["staff_id"],
                doctor_id=staff_row.get("doctor_id"),
                branch_id=staff_row.get("branch_id"),
            )

        # Check Patient
        patient_row = None
        if email or contact_details:
            await cur.execute(
                """
                SELECT patient_id, branch_id
                FROM patient
                WHERE (email IS NOT NULL AND LOWER(email) = LOWER(%s))
                   OR (contact_details IS NOT NULL AND contact_details = %s)
                LIMIT 1;
                """,
                (email or "", contact_details or "")
            )
            patient_row = await cur.fetchone()

        if patient_row:
            return AuthUser(
                user_id=user_id,
                user_type=UserType.PATIENT.value,
                role=UserRole.PATIENT.value,
                username=user_row.get("username"),
                email=email,
                first_name=user_row.get("first_name"),
                last_name=user_row.get("last_name"),
                patient_id=patient_row["patient_id"],
                branch_id=patient_row.get("branch_id"),
            )

        fallback_role = UserRole.ADMIN.value if "admin" in (user_row.get("username") or "").lower() else UserRole.PATIENT.value
        fallback_type = UserType.STAFF.value if fallback_role == UserRole.ADMIN.value else UserType.PATIENT.value
        return AuthUser(
            user_id=user_id,
            user_type=fallback_type,
            role=fallback_role,
            username=user_row.get("username"),
            email=email,
            first_name=user_row.get("first_name"),
            last_name=user_row.get("last_name"),
        )

