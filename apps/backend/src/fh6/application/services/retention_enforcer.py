"""T080: RetentionEnforcer (Clarification Q2 + FR-039a).

Two passes:
1. Age-based: delete sessions whose `started_at < now - retentionDays`.
2. Per-car size cap: while `bytes_used_by_car(car) > maxBytesPerCar`,
   delete that car's oldest closed session.

Skips the currently in-flight session (`ended_at IS NULL`) in both
passes. Cross-car isolation: a heavy car never evicts data belonging
to another car.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fh6.domain.entities.session import Session
from fh6.domain.ports.car_repository import CarRepository
from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.ports.session_repository import SessionRepository
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class RetentionPolicy:
    retention_days: int = 90
    max_bytes_per_car: int = 5_368_709_120  # 5 GiB default (Q2 / R-4)
    idle_interval_seconds: float = 600.0  # 10 min idle
    active_interval_seconds: float = 60.0  # 1 min active


@dataclass(slots=True)
class RetentionRun:
    aged_out: list[SessionId]
    capped_out: list[SessionId]
    skipped_in_flight: int


class RetentionEnforcer:
    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        car_repo: CarRepository,
        frame_store: FrameStore,
        policy: RetentionPolicy,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions = session_repo
        self._cars = car_repo
        self._store = frame_store
        self._policy = policy
        self._clock = clock
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    async def run_once(self) -> RetentionRun:
        now = self._clock()
        cutoff = now - timedelta(days=self._policy.retention_days)
        aged_out: list[SessionId] = []
        capped_out: list[SessionId] = []
        skipped = 0

        cars = await self._cars.list_all()
        for car in cars:
            sessions = await self._sessions.list_for_car(car.id, limit=10_000)
            # Pass 1: age-based.
            for s in sessions:
                if s.ended_at is None:
                    skipped += 1
                    continue
                if s.started_at < cutoff:
                    deleted = await self._delete_session(s)
                    if deleted:
                        aged_out.append(s.id)

            # Pass 2: per-car size cap. Re-fetch closed sessions sorted oldest-first.
            closed = sorted(
                (
                    s
                    for s in await self._sessions.list_for_car(car.id, limit=10_000)
                    if s.ended_at is not None
                ),
                key=lambda x: x.started_at,
            )
            cap = self._policy.max_bytes_per_car
            while await self._store.bytes_used_by_car(car.id) > cap and closed:
                victim = closed.pop(0)
                deleted = await self._delete_session(victim)
                if deleted:
                    capped_out.append(victim.id)

        return RetentionRun(
            aged_out=aged_out,
            capped_out=capped_out,
            skipped_in_flight=skipped,
        )

    async def _delete_session(self, session: Session) -> bool:
        # Defensive: never delete an in-flight session.
        if session.ended_at is None:
            return False
        await self._store.delete_session(session.id)
        return await self._sessions.delete(session.id)

    async def _run_forever(self, *, active_signal: asyncio.Event | None) -> None:
        try:
            while not self._stopped.is_set():
                try:
                    run = await self.run_once()
                    log.info(
                        "retention_run",
                        aged_out=len(run.aged_out),
                        capped_out=len(run.capped_out),
                        skipped_in_flight=run.skipped_in_flight,
                    )
                except Exception:  # pragma: no cover
                    log.exception("retention_run_failed")
                interval = (
                    self._policy.active_interval_seconds
                    if active_signal is not None and active_signal.is_set()
                    else self._policy.idle_interval_seconds
                )
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=interval)
                    return
                except TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    def start(self, *, active_signal: asyncio.Event | None = None) -> None:
        if self._task is not None:
            return
        self._stopped.clear()
        self._task = asyncio.create_task(
            self._run_forever(active_signal=active_signal),
            name="retention-enforcer",
        )

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None


__all__ = ["RetentionEnforcer", "RetentionPolicy", "RetentionRun"]
