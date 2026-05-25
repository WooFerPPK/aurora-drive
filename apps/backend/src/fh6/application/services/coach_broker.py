"""Coach-channel broker (application service, Phase 9).

Mirrors `LiveBroker`: publishes serialized coach callouts onto a
`MessageBroker`; the WS adapter in `interfaces/ws/coach.py` subscribes
and forwards to connected WS clients.

Availability gating (LLM dry-run, missing API key) lives here — gating
at the publisher means quiet engine state propagates to every worker
uniformly rather than being decided per-WS.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.domain.entities.coach_callout import CoachCallout
from fh6.domain.ports.messaging import MessageBroker
from fh6.infrastructure.messaging.inprocess_broker import InProcessBroker
from fh6.interfaces.ws.heartbeat import TICK_INTERVAL_SECONDS

SUBSCRIBER_QUEUE_CAPACITY = 32

CHANNEL_CALLOUTS = "coach:callouts"


class CoachBroker:
    def __init__(
        self,
        *,
        availability: CoachAvailabilityService,
        broker: MessageBroker | None = None,
        server_name: str = "fh6-backend/0.1.0",
        engine_enabled: Callable[[], bool] | None = None,
        heartbeat_interval_seconds: float | None = None,
        heartbeat_tick_seconds: float = TICK_INTERVAL_SECONDS,
    ) -> None:
        self._availability = availability
        self._broker = broker if broker is not None else InProcessBroker()
        self._owns_broker = broker is None
        self._server_name = server_name
        self._engine_enabled = engine_enabled or (lambda: True)
        self._hb_interval = heartbeat_interval_seconds
        self._hb_tick = heartbeat_tick_seconds

    # ---- public accessors --------------------------------------------

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def heartbeat_interval_seconds(self) -> float | None:
        return self._hb_interval

    @property
    def heartbeat_tick_seconds(self) -> float:
        return self._hb_tick

    @property
    def availability(self) -> CoachAvailabilityService:
        return self._availability

    def subscribe_callouts(self) -> Awaitable[AsyncIterator[bytes]]:
        return self._broker.subscribe(CHANNEL_CALLOUTS)

    # ---- publisher ---------------------------------------------------

    async def push_callout(self, callout: CoachCallout) -> None:
        if not self._engine_enabled():
            return
        availability = await self._availability.status()
        if not availability.available:
            return
        payload = _serialize_callout(callout)
        await self._broker.publish(CHANNEL_CALLOUTS, _encode(payload))

    # ---- lifecycle ---------------------------------------------------

    async def start(self) -> None:
        if self._owns_broker:
            await self._broker.start()

    async def stop(self) -> None:
        if self._owns_broker:
            await self._broker.stop()


def _serialize_callout(c: CoachCallout) -> dict[str, Any]:
    return {
        "type": "callout",
        "id": c.id,
        "atS": c.at_session_seconds,
        "priority": c.priority.value,
        "lap": int(c.lap_context.get("lap", 0)),
        "corner": str(c.lap_context.get("corner", "?")),
        "text": c.text,
        "cites": c.cites,
        "modelVersion": c.model_version,
        "voice": c.voice,
    }


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


__all__ = ["CHANNEL_CALLOUTS", "SUBSCRIBER_QUEUE_CAPACITY", "CoachBroker"]
