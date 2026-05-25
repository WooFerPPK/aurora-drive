from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.ids import CarId, SessionId
from tests.contract.fake_repos import InMemoryFrameStore


def _frame(
    *, session_id: str, t: datetime, x: float, y: float, z: float, yaw: float = 0.0
) -> DecodedFrame:
    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=int(t.timestamp() * 1000),
        engine={},
        drivetrain={},
        motion={
            "position": {"x": x, "y": y, "z": z},
            "orientation": {"yaw": yaw, "pitch": 0.0, "roll": 0.0},
            "speed_mps": 0.0,
        },
        inputs={},
        wheels={},
        world={},
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=SessionId(session_id),
        car_id=CarId("car_1_800"),
        received_at=t,
        raw=raw,
    )


@pytest.mark.asyncio
async def test_read_last_position_snapshot_returns_none_for_empty() -> None:
    store = InMemoryFrameStore()
    snap = await store.read_last_position_snapshot(SessionId("s1"))
    assert snap is None


@pytest.mark.asyncio
async def test_read_last_position_snapshot_returns_latest() -> None:
    store = InMemoryFrameStore()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(3):
        await store.append(
            _frame(
                session_id="s1",
                t=t0 + timedelta(seconds=i),
                x=float(i),
                y=0.0,
                z=0.0,
                yaw=0.1 * i,
            )
        )
    snap = await store.read_last_position_snapshot(SessionId("s1"))
    assert snap is not None
    assert snap.x == 2.0
    assert snap.yaw == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_read_position_track_orders_by_time_ascending() -> None:
    store = InMemoryFrameStore()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    # Append out of order.
    await store.append(_frame(session_id="s1", t=t0 + timedelta(seconds=2), x=2, y=0, z=0))
    await store.append(_frame(session_id="s1", t=t0, x=0, y=0, z=0))
    await store.append(_frame(session_id="s1", t=t0 + timedelta(seconds=1), x=1, y=0, z=0))
    track = await store.read_position_track(SessionId("s1"))
    assert [s.x for s in track] == [0.0, 1.0, 2.0]


@pytest.mark.asyncio
async def test_delete_frames_in_range_exclusive_bounds() -> None:
    store = InMemoryFrameStore()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        await store.append(
            _frame(
                session_id="s1",
                t=t0 + timedelta(seconds=i),
                x=float(i),
                y=0,
                z=0,
            )
        )
    # Delete (t0+1, t0+3) exclusive — should remove only t0+2.
    deleted = await store.delete_frames_in_range(
        SessionId("s1"),
        after=t0 + timedelta(seconds=1),
        before=t0 + timedelta(seconds=3),
    )
    assert deleted == 1
    track = await store.read_position_track(SessionId("s1"))
    xs = [s.x for s in track]
    assert xs == [0.0, 1.0, 3.0, 4.0]
