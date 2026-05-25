"""Clarification Q1: ResumeSessionOnRestart truth table.

Four cases:
- within-threshold + matching car → RESUMED
- within-threshold + different car → FINALIZED_PRIOR (split)
- over-threshold + matching car → FINALIZED_PRIOR (split)
- over-threshold + different car → FINALIZED_PRIOR (split)

Plus: no-prior-session → NO_PRIOR_SESSION.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.session_manager import SessionManager
from fh6.application.use_cases.resume_session_on_restart import (
    ResumeOutcome,
    ResumeSessionOnRestart,
)
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder


class _MemSessionRepo:
    """Minimal in-memory session repository for unit tests."""

    def __init__(self) -> None:
        self._by_id: dict[str, Session] = {}

    async def save(self, session: Session) -> None:
        self._by_id[session.id] = session

    async def get(self, session_id: SessionId) -> Session | None:
        return self._by_id.get(session_id)

    async def latest_in_flight(self) -> Session | None:
        candidates = [s for s in self._by_id.values() if s.ended_at is None]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.started_at)

    async def list_for_car(self, car_id: CarId, limit: int = 50) -> list[Session]:
        return [s for s in self._by_id.values() if s.car_id == car_id][:limit]

    async def delete(self, session_id: SessionId) -> bool:
        return self._by_id.pop(session_id, None) is not None


@pytest.fixture
def repo() -> _MemSessionRepo:
    return _MemSessionRepo()


def _seed_prior_session(repo: _MemSessionRepo, car_id: CarId, started_at: datetime) -> Session:
    s = Session(
        id=SessionId(f"s_{started_at.isoformat()}_{car_id}"),
        car_id=car_id,
        type=SessionType.RACE,
        started_at=started_at,
    )

    # Inject (sync — _MemSessionRepo dict assignment is safe here).
    repo._by_id[s.id] = s
    return s


async def test_no_prior_session(repo: _MemSessionRepo, golden_packet: bytes) -> None:
    sm = SessionManager(silence_seconds=60.0)
    uc = ResumeSessionOnRestart(repo, sm)
    raw = FH6PacketDecoder().decode(golden_packet)
    result = await uc.apply(
        first_packet_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
        first_packet_raw=raw,
        last_frame_at=None,
    )
    assert result.outcome == ResumeOutcome.NO_PRIOR_SESSION
    assert sm.current is None


async def test_resume_within_threshold_same_car(
    repo: _MemSessionRepo, golden_packet: bytes
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    # car_id derived from packet
    car_id = CarId("car_2451_812")
    last = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    started = last - timedelta(minutes=10)
    prior = _seed_prior_session(repo, car_id, started)

    uc = ResumeSessionOnRestart(repo, sm)
    result = await uc.apply(
        first_packet_at=last + timedelta(seconds=30),
        first_packet_raw=raw,
        last_frame_at=last,
    )
    assert result.outcome == ResumeOutcome.RESUMED
    assert result.resumed is not None
    assert result.resumed.id == prior.id
    assert sm.current is not None
    assert sm.current.id == prior.id


async def test_finalize_within_threshold_different_car(
    repo: _MemSessionRepo, golden_packet: bytes
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    # Prior session was a DIFFERENT car id
    other_car_id = CarId("car_9999_820")
    last = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    prior = _seed_prior_session(repo, other_car_id, last - timedelta(minutes=10))

    uc = ResumeSessionOnRestart(repo, sm)
    result = await uc.apply(
        first_packet_at=last + timedelta(seconds=30),
        first_packet_raw=raw,
        last_frame_at=last,
    )
    assert result.outcome == ResumeOutcome.FINALIZED_PRIOR
    assert result.finalized is not None
    assert result.finalized.id == prior.id
    assert result.finalized.ended_at is not None
    assert result.finalized.closed_reason.value == "restart_finalize"
    assert sm.current is None  # ready for next packet to open new


async def test_finalize_over_threshold_same_car(
    repo: _MemSessionRepo, golden_packet: bytes
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    car_id = CarId("car_2451_812")
    last = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    prior = _seed_prior_session(repo, car_id, last - timedelta(minutes=10))

    uc = ResumeSessionOnRestart(repo, sm)
    result = await uc.apply(
        first_packet_at=last + timedelta(seconds=120),  # > 60s
        first_packet_raw=raw,
        last_frame_at=last,
    )
    assert result.outcome == ResumeOutcome.FINALIZED_PRIOR
    assert result.finalized is not None
    assert result.finalized.id == prior.id
    assert sm.current is None


async def test_finalize_over_threshold_different_car(
    repo: _MemSessionRepo, golden_packet: bytes
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    other_car_id = CarId("car_9999_820")
    last = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    prior = _seed_prior_session(repo, other_car_id, last - timedelta(minutes=10))

    uc = ResumeSessionOnRestart(repo, sm)
    result = await uc.apply(
        first_packet_at=last + timedelta(seconds=120),
        first_packet_raw=raw,
        last_frame_at=last,
    )
    assert result.outcome == ResumeOutcome.FINALIZED_PRIOR
    assert result.finalized is not None
    assert result.finalized.id == prior.id


async def test_no_last_frame_at_treated_as_over_threshold(
    repo: _MemSessionRepo, golden_packet: bytes
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    car_id = CarId("car_2451_812")
    _seed_prior_session(repo, car_id, datetime(2026, 5, 17, 11, 0, 0, tzinfo=UTC))

    uc = ResumeSessionOnRestart(repo, sm)
    result = await uc.apply(
        first_packet_at=datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC),
        first_packet_raw=raw,
        last_frame_at=None,
    )
    assert result.outcome == ResumeOutcome.FINALIZED_PRIOR
