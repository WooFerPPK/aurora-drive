from __future__ import annotations

from typing import Any, Protocol


class LayoutsRepository(Protocol):
    async def get(self, page_id: str) -> dict[str, Any] | None: ...

    async def put(self, page_id: str, layout: dict[str, Any]) -> None: ...

    async def patch(self, page_id: str, partial: dict[str, Any]) -> dict[str, Any]: ...
