"""SQLAlchemy async engine + session."""
import re
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


def _normalize_db_url(url: str) -> tuple[str, dict]:
    """Konversi URL Postgres + return connect_args yang sesuai.

    Fly Postgres attach men-set DATABASE_URL dengan scheme `postgres://` dan
    biasanya `?sslmode=disable` karena hostname `.flycast` / `.internal`
    sudah pakai WireGuard mesh (encrypted di network layer).

    Asyncpg tidak mengenal `sslmode=` (itu psycopg2 param), tapi punya
    parameter `ssl=False` lewat connect_args.
    """
    connect_args: dict = {}

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Bila URL mengindikasikan no-SSL (sslmode=disable atau hostname internal Fly),
    # pakai ssl=False di asyncpg
    if (
        "sslmode=disable" in url
        or ".flycast" in url
        or ".internal" in url
    ):
        connect_args["ssl"] = False

    # Strip sslmode= param (asyncpg tidak mengenalnya)
    url = re.sub(r"[?&]sslmode=\w+", "", url)
    return url, connect_args


class Base(DeclarativeBase):
    """Base class untuk semua SQLAlchemy models."""

    pass


_db_url, _connect_args = _normalize_db_url(settings.database_url)
engine = create_async_engine(
    _db_url,
    echo=settings.is_dev,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield 1 session per request."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise