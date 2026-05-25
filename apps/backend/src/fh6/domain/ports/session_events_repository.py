"""Port for persisting + reading per-session event logs.

Drives the historical "highlight reel" view on `SessionDetail`. The
production adapter is Postgres-backed; tests substitute the in-memory
fake from `tests/contract/fake_repos.py`.
"""

from __future__ import annotations

from typing import Protocol

from fh6.domain.value_objects.session_event import SessionEvent


class SessionEventsRepository(Protocol):
    async def save_many(self, events: list[SessionEvent]) -> None: ...

    async def list_for_session(self, session_id: str) -> list[SessionEvent]: ...
