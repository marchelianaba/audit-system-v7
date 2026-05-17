"""Inisialisasi database: buat tabel + seed user uji.

Dipanggil saat first deploy (lihat fly.toml `release_command`) atau manual:
    python -m app.init_db
"""
import asyncio

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Role, User


SEED_USERS = [
    {
        "email": "auditor.at@komdigi.go.id",
        "nama_lengkap": "Sarah Aulia",
        "nip": "198501012010011001",
        "role_default": Role.AT,
    },
    {
        "email": "auditor.kt@komdigi.go.id",
        "nama_lengkap": "Budi Hartono",
        "nip": "197505152005011002",
        "role_default": Role.KT,
    },
    {
        "email": "inspektorat2.kominfo.2@gmail.com",
        "nama_lengkap": "Inspektorat II Komdigi",
        "nip": "197001012000011001",
        "role_default": Role.PM,
    },
]


async def init():
    print("[init_db] Membuat tabel ...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("[init_db] Seed users ...")
    async with SessionLocal() as session:
        for u in SEED_USERS:
            existing = (
                await session.execute(select(User).where(User.email == u["email"]))
            ).scalar_one_or_none()
            if existing:
                print(f"  - {u['email']} sudah ada, skip")
                continue
            session.add(User(**u))
            print(f"  + {u['email']} ({u['role_default'].value})")
        await session.commit()
    print("[init_db] Selesai.")


if __name__ == "__main__":
    asyncio.run(init())
