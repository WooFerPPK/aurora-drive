"""Unit tests for InMemoryLapRepository (the in-memory fake used in contract tests).

Verifies the upsert semantics (rewind overwrites) and list ordering so
the fake behaves identically to the Postgres adapter contract.
"""

from __future__ import annotations

import asyncio

import pytest

from fh6.domain.value_objects.completed_lap import CompletedLap
from fh6.domain.value_objects.ids import SessionId
from tests.contract.fake_repos import InMemoryLapRepository


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def repo() -> InMemoryLapRepository:
    return InMemoryLapRepository()


def test_upsert_and_list(repo: InMemoryLapRepository) -> None:
    sid = SessionId("s_1")
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=0, lap_time_s=57.2)))
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=1, lap_time_s=55.0)))

    laps = _run(repo.list_laps_for_session(sid))
    assert len(laps) == 2
    assert laps[0].lap_number == 0
    assert abs(laps[0].lap_time_s - 57.2) < 0.001
    assert laps[1].lap_number == 1
    assert abs(laps[1].lap_time_s - 55.0) < 0.001


def test_upsert_overwrites_on_rewind(repo: InMemoryLapRepository) -> None:
    sid = SessionId("s_1")
    # Provisional final lap recorded at close.
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=1, lap_time_s=30.0)))
    # True completion after reopen is longer.
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=1, lap_time_s=55.0)))

    laps = _run(repo.list_laps_for_session(sid))
    assert len(laps) == 1
    assert abs(laps[0].lap_time_s - 55.0) < 0.001


def test_list_empty_session(repo: InMemoryLapRepository) -> None:
    laps = _run(repo.list_laps_for_session(SessionId("s_unknown")))
    assert laps == []


def test_min_lap_time(repo: InMemoryLapRepository) -> None:
    sid = SessionId("s_1")
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=0, lap_time_s=60.0)))
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=1, lap_time_s=55.0)))
    _run(repo.upsert_lap(sid, CompletedLap(lap_number=2, lap_time_s=58.0)))

    result = _run(repo.min_lap_time_for_session(sid))
    assert result is not None and abs(result - 55.0) < 0.001


def test_min_lap_time_empty(repo: InMemoryLapRepository) -> None:
    result = _run(repo.min_lap_time_for_session(SessionId("s_none")))
    assert result is None


def test_laps_isolated_between_sessions(repo: InMemoryLapRepository) -> None:
    s1, s2 = SessionId("s_1"), SessionId("s_2")
    _run(repo.upsert_lap(s1, CompletedLap(lap_number=0, lap_time_s=50.0)))
    _run(repo.upsert_lap(s2, CompletedLap(lap_number=0, lap_time_s=80.0)))

    assert len(_run(repo.list_laps_for_session(s1))) == 1
    assert len(_run(repo.list_laps_for_session(s2))) == 1
