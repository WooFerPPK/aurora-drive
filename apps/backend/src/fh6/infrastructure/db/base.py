from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, cast

from sqlalchemy import DateTime
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all FH6 models."""

    type_annotation_map: ClassVar[dict[type, DateTime]] = {
        datetime: DateTime(timezone=True),
    }


def make_engine(dsn: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(dsn, echo=echo, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def rowcount(result: Result[Any]) -> int:
    """Return DML row count, narrowing `Result[Any]` to `CursorResult`.

    `AsyncSession.execute` is typed as `Result[T]` in the SQLAlchemy stubs,
    but DML statements actually return a `CursorResult` at runtime — that's
    where `.rowcount` lives. Centralizing the cast keeps repo call sites
    free of repeated `# type: ignore[attr-defined]` noise.
    """
    return cast("CursorResult[Any]", result).rowcount or 0
