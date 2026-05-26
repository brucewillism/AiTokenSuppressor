"""Authentication endpoints."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

ADMIN_USERS = {
    "admin": hash_password("admin123"),
}


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest) -> TokenResponse:
    hashed = ADMIN_USERS.get(request.username)
    if not hashed or not verify_password(request.password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(
        {"sub": request.username},
        expires_delta=timedelta(minutes=settings.jwt_expire_minutes),
    )
    return TokenResponse(access_token=token)
