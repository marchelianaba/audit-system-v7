"""Routes manajemen penugasan."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Penugasan, PenugasanStatus, Role, User
from app.schemas import PenugasanCreate, PenugasanOut
from app.storage import gen_kode_penugasan, penugasan_folder

router = APIRouter(prefix="/penugasan", tags=["penugasan"])


@router.post("", response_model=PenugasanOut, status_code=status.HTTP_201_CREATED)
async def create_penugasan(
    payload: PenugasanCreate,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PenugasanOut:
    user, role = current
    kode = gen_kode_penugasan(payload.skill.value)
    folder = penugasan_folder(kode)

    p = Penugasan(
        kode=kode,
        obyek=payload.obyek,
        skill=payload.skill,
        nomor_st=payload.nomor_st,
        tanggal_st=payload.tanggal_st,
        status=PenugasanStatus.DRAFT,
        ketua_tim_id=user.id if role in (Role.KT, Role.PT, Role.PM) else None,
        folder_path=str(folder),
    )
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return PenugasanOut.model_validate(p)


@router.get("", response_model=list[PenugasanOut])
async def list_penugasan(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PenugasanOut]:
    rows = (await db.execute(select(Penugasan).order_by(Penugasan.created_at.desc()))).scalars().all()
    return [PenugasanOut.model_validate(r) for r in rows]


@router.get("/{penugasan_id}", response_model=PenugasanOut)
async def get_penugasan(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PenugasanOut:
    p = (
        await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")
    return PenugasanOut.model_validate(p)
