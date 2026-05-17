"""Entry point FastAPI."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routes import agen, auth, dokumen, penugasan

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Buat tabel saat startup (idempoten). Untuk migrasi lebih ketat pakai Alembic.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Audit AI v7",
    version="0.1.0",
    description="Backend Audit AI v7 — Inspektorat II Komdigi",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(penugasan.router)
app.include_router(dokumen.router)
app.include_router(agen.router)


@app.get("/", tags=["meta"])
async def root():
    return {
        "name": "Audit AI v7",
        "version": "0.1.0",
        "env": settings.app_env,
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
