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
        "email": "auditor.at2@komdigi.go.id",
        "nama_lengkap": "Citra Lestari",
        "nip": "198803152012012002",
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
        "role_default": Role.PT,
    },
]


async def init():
    print("[init_db] Membuat tabel ...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("[init_db] Seed users (upsert: insert kalau belum ada, update kalau role/nama/nip beda) ...")
    async with SessionLocal() as session:
        for u in SEED_USERS:
            existing = (
                await session.execute(select(User).where(User.email == u["email"]))
            ).scalar_one_or_none()
            if existing:
                # Upsert: cek apakah field-field penting perlu di-update
                # (mis. migrasi PM → PT di production yang sudah punya user existing)
                changed = []
                if existing.role_default != u["role_default"]:
                    changed.append(
                        f"role_default: {existing.role_default.value if hasattr(existing.role_default, 'value') else existing.role_default} → {u['role_default'].value}"
                    )
                    existing.role_default = u["role_default"]
                if existing.nama_lengkap != u["nama_lengkap"]:
                    changed.append(f"nama_lengkap: {existing.nama_lengkap!r} → {u['nama_lengkap']!r}")
                    existing.nama_lengkap = u["nama_lengkap"]
                if existing.nip != u["nip"]:
                    changed.append(f"nip: {existing.nip!r} → {u['nip']!r}")
                    existing.nip = u["nip"]
                if changed:
                    print(f"  ~ {u['email']} UPDATE: {', '.join(changed)}")
                else:
                    print(f"  - {u['email']} sudah ada, tidak ada perubahan")
                continue
            session.add(User(**u))
            print(f"  + {u['email']} ({u['role_default'].value})")
        await session.commit()
    print("[init_db] Selesai.")


if __name__ == "__main__":
    asyncio.run(init())
