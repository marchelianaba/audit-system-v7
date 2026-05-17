"""Routes autentikasi: login sederhana berbasis email + NIP."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_session_token
from app.database import get_db
from app.models import Role, User
from app.schemas import LoginRequest, SessionOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionOut)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)) -> SessionOut:
    user = (
        await db.execute(select(User).where(User.email == req.email))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User tidak ditemukan")
    if len(req.nip) != 18 or not req.nip.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "NIP harus 18 digit angka")
    # Prototype: NIP cocok dengan yang di seed → login OK.
    if user.nip != req.nip:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "NIP tidak cocok")

    role = req.role or Role(user.role_default)
    token = create_session_token(user.id, role)
    return SessionOut(user=UserOut.model_validate(user), role_aktif=role, token=token)
