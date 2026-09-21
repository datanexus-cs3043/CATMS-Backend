import logging
from typing import Callable, List, Optional
import jwt
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings
from app.auth.security import decode_access_token, verify_csrf_token
from app.auth.schemas import JWTPayload, UserType, UserRole

logger = logging.getLogger("medsync.auth.dependencies")
bearer_scheme = HTTPBearer(auto_error=False)


# ==========================================
# 1. Authentication Dependency
# ==========================================

async def get_current_user(
    request: Request,
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> JWTPayload:
    """
    Retrieves and validates the JWT from either:
    1. The HttpOnly cookie (primary for browser / React).
    2. The Authorization header (Bearer token fallback for API testing).
    """
    token = request.cookies.get(settings.COOKIE_NAME)
    
    # Fallback to Authorization: Bearer <token>
    if not token and bearer_token:
        token = bearer_token.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided."
        )

    try:
        payload = decode_access_token(token)
        return JWTPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again."
        )
    except jwt.PyJWTError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )


async def require_authenticated_user(
    current_user: JWTPayload = Depends(get_current_user)
) -> JWTPayload:
    """Alias dependency requiring any valid authenticated user."""
    return current_user


# ==========================================
# 2. Role-Based Authorization Dependencies
# ==========================================

def require_role(*allowed_roles: str) -> Callable:
    """
    Factory creating a FastAPI dependency to enforce one or more user roles.
    Example:
        @router.get('/admin-report', dependencies=[Depends(require_role('admin'))])
    """
    normalized_allowed = {r.lower() for r in allowed_roles}

    async def role_checker(
        current_user: JWTPayload = Depends(get_current_user)
    ) -> JWTPayload:
        if current_user.role.lower() not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: Action requires one of the following roles: {list(allowed_roles)}."
            )
        return current_user

    return role_checker


async def require_staff(
    current_user: JWTPayload = Depends(get_current_user)
) -> JWTPayload:
    """Enforces that the user is a Staff member (Admin, Manager, Doctor, Receptionist/Cashier)."""
    if current_user.user_type != UserType.STAFF.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Staff credentials required."
        )
    return current_user


async def require_patient(
    current_user: JWTPayload = Depends(get_current_user)
) -> JWTPayload:
    """Enforces that the user is a Patient."""
    if current_user.user_type != UserType.PATIENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Patient credentials required."
        )
    return current_user


# ==========================================
# 3. Data-Level & Ownership Authorization
# ==========================================

def verify_branch_access(target_branch_id: int, current_user: JWTPayload) -> bool:
    """
    Verifies branch-level access:
    - Admin has system-wide access across all branches.
    - Branch Managers and Receptionists are strictly restricted to their assigned branch.
    """
    if current_user.role.lower() == UserRole.ADMIN.value:
        return True

    if current_user.branch_id is not None and current_user.branch_id != target_branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access forbidden: You do not have permission to access data for Branch {target_branch_id}."
        )
    return True


def verify_patient_ownership(target_patient_id: int, current_user: JWTPayload) -> bool:
    """
    Verifies patient data ownership:
    - Staff members have access to patient records for clinical & administrative duties.
    - Patients can ONLY access records matching their own patient_id.
    """
    if current_user.user_type == UserType.STAFF.value:
        return True

    if current_user.patient_id != target_patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You are not authorized to view or modify this patient record."
        )
    return True


# ==========================================
# 4. CSRF Protection Dependency
# ==========================================

async def require_csrf(request: Request) -> None:
    """
    Validates the X-CSRF-Token header on state-changing HTTP requests (POST, PUT, PATCH, DELETE).
    Safe methods (GET, HEAD, OPTIONS) are bypassed.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_token = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken")
        if not csrf_token or not verify_csrf_token(csrf_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed: Missing or invalid X-CSRF-Token header."
            )
