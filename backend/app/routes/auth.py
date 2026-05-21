"""Routes autentikasi — prototype login dengan role saja.

Karena ini prototype internal, login tidak butuh password atau NIP.
Auditor cukup pilih role di UI, backend auto-pick user seed pertama
yang punya `role_default == role` tersebut.

Produksi nanti diganti SSO Komdigi (OIDC).
"""
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
    """Login dengan role saja (prototype).

    - Wajib: `role` (AT/KT/PT/PM)
    - Optional: `email` — kalau diberikan, pilih user tertentu dengan email itu
    - Optional: `nip` — di prototype ini diabaikan (boleh dikirim untuk forward-compat)

    Strategy pemilihan user:
    1. Bila `email` diberikan → pilih user dengan email itu (tidak peduli role_default)
    2. Bila `email` kosong → pilih user pertama yang `role_default == role`
    3. Bila tidak ada match → 404
    """
    user: User | None = None

    if req.email:
        user = (
            await db.execute(select(User).where(User.email == req.email))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"User dengan email {req.email} tidak ditemukan",
            )
    else:
        # Pick user pertama yang role_default match
        user = (
            await db.execute(
                select(User)
                .where(User.role_default == req.role)
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Belum ada user dengan role default {req.role.value}. "
                f"Edit backend/app/init_db.py untuk seed user, lalu jalankan ulang.",
            )

    token = create_session_token(user.id, req.role)
    return SessionOut(
        user=UserOut.model_validate(user),
        role_aktif=req.role,
        token=token,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(
    role: Role | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    """Daftar user seed (opsional filter by role_default).

    Publik (prototype) — dipakai layar login untuk menampilkan pilihan orang
    saat satu role punya >1 user (mis. beberapa Anggota Tim), dan dipakai KT
    untuk dropdown assignment sasaran ke nama AT yang sebenarnya.
    """
    stmt = select(User).order_by(User.id)
    if role is not None:
        stmt = stmt.where(User.role_default == role)
    rows = (await db.execute(stmt)).scalars().all()
    return [UserOut.model_validate(u) for u in rows]
