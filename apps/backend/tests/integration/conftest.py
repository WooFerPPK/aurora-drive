"""Integration fixtures backed by a real Postgres + Timescale instance.

Setup expectation: an `fh6_test` database exists, owned by `fh6`, with
the `timescaledb` extension pre-installed. The fh6 role is intentionally
not granted CREATEDB / superuser, so the database itself is one-time
infrastructure (see `make db.test.setup`). Each test truncates the
tables it touches; the schema is preserved across the session.

DSN: `FH6_TEST_DB_DSN`, defaulting to the same fh6 user as prod but on
the `fh6_test` database. Tests are auto-skipped when neither
`FH6_TEST_DB_DSN` nor `FH6_DB_DSN` is reachable.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from fh6.infrastructure.db.models.cars import CarModel
from fh6.infrastructure.db.models.sessions import SessionModel

DEFAULT_TEST_DSN = "postgresql+asyncpg://fh6:fh6@127.0.0.1:5432/fh6_test"

# Tables that 2d adapters touch. Truncated before each integration test
# so cases stay independent without dropping/recreating the schema. New
# adapter PRs append their tables here. Order is FK-respecting only when
# CASCADE is not used; we use CASCADE so order doesn't matter, but
# keeping parents last is good documentation.
_TRUNCATE_TABLES: list[str] = [
    "coach_insights",
    "coach_callouts",
    "mistakes",
    "predictions",
    "replays",
    "layouts",
    "driver_profile",
    "sessions",
    "tracks",
    "cars",
]


def _test_dsn() -> str:
    explicit = os.environ.get("FH6_TEST_DB_DSN")
    if explicit:
        return explicit
    prod = os.environ.get("FH6_DB_DSN")
    if prod and prod.endswith("/fh6"):
        return prod[:-4] + "/fh6_test"
    return DEFAULT_TEST_DSN


@pytest_asyncio.fixture(scope="session")
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    # NullPool: each acquire opens a fresh asyncpg connection. pytest-asyncio
    # runs each test in its own event loop, and asyncpg connections cannot
    # be shared across loops — pooling would otherwise raise
    # "another operation is in progress". The connection-open cost is
    # negligible for a local Postgres.
    engine = create_async_engine(_test_dsn(), future=True, echo=False, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"fh6_test database not reachable: {exc!s}")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
def pg_sessionmaker(pg_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(pg_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def pg_db(
    pg_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Truncate adapter tables before each test, then yield the sessionmaker.

    CASCADE so foreign-key chains (insights → sessions, etc.) clear in
    one statement. RESTART IDENTITY is harmless for our string-PK tables
    and future-proofs against an integer-PK table joining the list.
    """
    async with pg_sessionmaker() as db:
        stmt = "TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE;"
        await db.execute(text(stmt))
        await db.commit()
    yield pg_sessionmaker


@pytest_asyncio.fixture
async def seeded_session_id(
    pg_db: async_sessionmaker[AsyncSession],
) -> str:
    """Insert a parent Car + Session so FK-bearing adapter rows can attach.

    Returns the session id; callers can build entities against it without
    worrying about FK violations. The truncate fixture wipes both rows
    before the next test.
    """
    session_id = "ses_test_0001"
    car_id = "car_test_0001"
    async with pg_db() as db:
        db.add(
            CarModel(
                id=car_id,
                display_name="Test Car",
                short_name="TC",
                car_ordinal=1,
                car_class="A",
                performance_index=800,
                drivetrain="AWD",
                car_group=0,
            )
        )
        db.add(
            SessionModel(
                id=session_id,
                car_id=car_id,
                type="free_roam",
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()
    return session_id
