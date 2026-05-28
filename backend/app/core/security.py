"""JWT and API key authentication."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and len(token) > 20


def _is_valid_api_key(candidate: str | None) -> bool:
    if not candidate:
        return False
    expected = settings.api_key.strip()
    provided = candidate.strip()
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT. Use ATS API_KEY as Bearer token or X-API-Key header.",
        ) from exc


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if not _is_valid_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Send header X-API-Key with your ATS API_KEY.",
        )
    return api_key.strip()  # type: ignore[union-attr]


async def verify_jwt_or_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
) -> dict[str, Any]:
    if _is_valid_api_key(api_key):
        return {"sub": "api_key", "type": "api_key"}

    if credentials:
        token = credentials.credentials.strip()

        if _is_valid_api_key(token):
            return {"sub": "api_key", "type": "api_key_bearer"}

        # Chaves de provedores (OpenAI/Groq) não são JWT — mensagem clara
        if token.startswith(("sk-", "gsk_", "gsk-", "xai-")):
            logger.warning(
                "auth_provider_key_rejected",
                hint="client_sent_llm_key_instead_of_ats_api_key",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Invalid API key: you sent an LLM provider key (sk-/gsk_). "
                    "Use the ATS API_KEY from your .env (e.g. ats-super-api-key) in "
                    "Authorization: Bearer <API_KEY> or X-API-Key."
                ),
            )

        if _looks_like_jwt(token):
            payload = decode_access_token(token)
            return payload

        logger.warning("auth_invalid_bearer", token_prefix=token[:8] if token else "")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid API key. Use ATS API_KEY from .env as Bearer token "
                "or X-API-Key header (not OpenAI/Groq keys)."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Send Authorization: Bearer <API_KEY> or X-API-Key.",
        headers={"WWW-Authenticate": "Bearer"},
    )
