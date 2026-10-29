from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import load_settings

settings = load_settings()


class Base(DeclarativeBase):
    pass


# pool_pre_ping issues a cheap SELECT before each connection checkout to detect
# stale connections — important for Neon, which drops idle connections aggressively.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)