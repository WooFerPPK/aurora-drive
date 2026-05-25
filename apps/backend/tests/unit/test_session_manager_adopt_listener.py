from __future__ import annotations

from datetime import UTC, datetime

from fh6.application.services.session_manager import SessionManager
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId


def _session() -> Session:
    return Session(
        id=SessionId("s_rewind"),
        car_id=CarId("car_1_800"),
        type=SessionType.RACE,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_adopt_fires_registered_listeners() -> None:
    sm = SessionManager(silence_seconds=60.0)
    calls: list[SessionId] = []
    sm.add_adopt_listener(lambda s, _at: calls.append(s.id))
    sm.adopt(_session(), datetime(2026, 1, 1, tzinfo=UTC))
    assert calls == [SessionId("s_rewind")]


def test_adopt_fires_all_listeners_in_registration_order() -> None:
    sm = SessionManager(silence_seconds=60.0)
    order: list[str] = []
    sm.add_adopt_listener(lambda *_: order.append("a"))
    sm.add_adopt_listener(lambda *_: order.append("b"))
    sm.adopt(_session(), datetime(2026, 1, 1, tzinfo=UTC))
    assert order == ["a", "b"]


def test_adopt_listener_exception_does_not_block_other_listeners() -> None:
    sm = SessionManager(silence_seconds=60.0)
    fired: list[str] = []

    def boom(_s: Session, _at: datetime) -> None:
        raise RuntimeError("boom")

    sm.add_adopt_listener(boom)
    sm.add_adopt_listener(lambda *_: fired.append("ok"))
    sm.adopt(_session(), datetime(2026, 1, 1, tzinfo=UTC))
    assert fired == ["ok"]
