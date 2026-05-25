from __future__ import annotations

from datetime import datetime
from typing import Protocol

from fh6.domain.entities.session import Session
from fh6.domain.value_objects.ids import CarId, SessionId


class SessionRepository(Protocol):
    async def save(self, session: Session) -> None: ...

    async def get(self, session_id: SessionId) -> Session | None: ...

    async def latest_in_flight(self) -> Session | None: ...

    async def list_for_car(self, car_id: CarId, limit: int = 50) -> list[Session]: ...

    async def list_all(self, limit: int = 10_000) -> list[Session]: ...

    async def delete(self, session_id: SessionId) -> bool: ...

    async def delete_all(self) -> int: ...

    async def rename(self, session_id: SessionId, name: str | None) -> Session | None: ...

    async def set_bookmark(self, session_id: SessionId, bookmarked: bool) -> Session | None: ...

    async def finalize_stale(
        self,
        *,
        older_than: datetime,
        except_id: SessionId | None,
    ) -> int: ...
