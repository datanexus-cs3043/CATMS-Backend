from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from psycopg import AsyncConnection

from app.core.config import settings
from app.core.database import get_db
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    CSRFResponse,
    AuthUser,
    JWTPayload,
)
from app.auth.security import (
    create_access_token,
    decode_access_token,
    generate_csrf_token,
)
from app.auth.service import authenticate_user, get_user_by_id
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ==========================================
# 1. Login Endpoint
# ==========================================

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User Login",
    description="Authenticates staff or patient users, creates a JWT, and sets an HttpOnly session cookie.",
)
async def login(
    credentials: LoginRequest,
    response: Response,
    conn: AsyncConnection = Depends(get_db)
):
    user: AuthUser = await authenticate_user(
        conn=conn,
        username=credentials.username,
        plain_password=credentials.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Prepare JWT claims (no passwords, hashes, or medical data)
    jwt_claims = {
        "user_id": user.user_id,
        "user_type": user.user_type,
        "role": user.role,
        "staff_id": user.staff_id,
        "patient_id": user.patient_id,
        "doctor_id": user.doctor_id,
        "branch_id": user.branch_id,
    }
    access_token = create_access_token(jwt_claims)

    # Set JWT in secure HttpOnly cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    return LoginResponse(
        message="Login successful",
        user=user,
        access_token=access_token,
        token_type="bearer",
    )


# ==========================================
# 2. Logout Endpoint
# ==========================================

@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="User Logout",
    description="Clears the HttpOnly authentication cookie to invalidate the session.",
)
async def logout(response: Response):
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return LogoutResponse(message="Logout successful")


# ==========================================
# 3. Current User Profile Endpoint
# ==========================================

@router.get(
    "/me",
    response_model=AuthUser,
    summary="Get Current User",
    description="Reads the HttpOnly cookie and returns the currently authenticated user's profile and role.",
)
async def get_me(
    current_user: JWTPayload = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_db)
):
    user = await get_user_by_id(conn, current_user.user_id)
    if not user:
        # Fallback to token claims if DB record is not found
        return AuthUser(
            user_id=current_user.user_id,
            user_type=current_user.user_type,
            role=current_user.role,
            staff_id=current_user.staff_id,
            patient_id=current_user.patient_id,
            doctor_id=current_user.doctor_id,
            branch_id=current_user.branch_id,
        )
    return user


# ==========================================
# 4. CSRF Token Endpoint
# ==========================================

@router.get(
    "/csrf",
    response_model=CSRFResponse,
    summary="Get CSRF Token",
    description="Returns a time-limited HMAC-signed CSRF token for the frontend to include in state-changing requests (X-CSRF-Token header).",
)
async def get_csrf_token(request: Request):
    # If user is already logged in, bind token to user ID, otherwise guest
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    user_id_str = "guest"
    if token:
        try:
            payload = decode_access_token(token)
            user_id_str = str(payload.get("user_id", "authenticated"))
        except Exception:
            pass

    csrf_token = generate_csrf_token(user_id_str)
    return CSRFResponse(csrf_token=csrf_token)

