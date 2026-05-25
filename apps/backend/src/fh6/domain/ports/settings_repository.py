from __future__ import annotations

from typing import Any, Protocol


class SettingsRepository(Protocol):
    async def get_all(self) -> dict[str, Any]: ...

    async def get_group(self, key: str) -> dict[str, Any]: ...

    async def patch(self, partial: dict[str, Any]) -> dict[str, Any]: ...
