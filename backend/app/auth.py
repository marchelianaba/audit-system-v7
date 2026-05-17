"""Autentikasi sederhana untuk prototype.

Tidak ada password — auditor login dengan email + NIP. Untuk produksi nanti
diganti SSO Komdigi (OIDC).
"""
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Role, User

settings = get_settings()

ALGORITHM = "HS256"
EXPIRE_HOURS = 12


def create_session_token(user_id: int, role: Role) -> str:
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "exp": datetime.utcnow() + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def decode_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid") from e


async def get_current_user(
    request: Request,
    _token: str | None = None,  # fallback dari query param untuk SSE EventSource
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Role]:
    """Ambil user dari header Authorization Bearer ATAU query param _token.

    EventSource (SSE) di browser tidak support custom headers, jadi token
    dikirim via query param untuk endpoint streaming.
    """
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif _token:
        token = _token

    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak ada")

    payload = decode_session_token(token)
    user_id = int(payload["sub"])
    role = Role(payload["role"])

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak ditemukan")
    return user, role

def require_role(*allowed: Role):
    """Dependency factory: hanya boleh dipanggil bila role aktif termasuk `allowed`."""

    async def _checker(
        current: tuple[User, Role] = Depends(get_current_user),
    ) -> tuple[User, Role]:
        _, role = current
        if role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Aksi ini hanya untuk role: {[r.value for r in allowed]}",
            )
        return current

    return _checker
