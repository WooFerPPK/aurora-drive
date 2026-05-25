"""T076: contract test for `/api/sessions` (API spec §3)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services import derivations, modeled_placeholder
from fh6.application.services.session_manager import SessionManager, attach_session
from fh6.domain.entities.car import Car
from fh6.domain.entities.frame import FrameRaw
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.domain.value_objects.session_event import SessionEvent
from fh6.interfaces.rest.sessions_router import router as sessions_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryCoachRepository,
    InMemoryFrameStore,
    InMemoryLapRepository,
    InMemorySessionEventsRepository,
    InMemorySessionRepository,
)


def _raw(ts_ms: int = 1000, x: float = 0.0) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=ts_ms,
        engine={
            "rpm": 6000.0,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 11.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": 4, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "position": {"x": x, "y": 0.0, "z": 0.0},
        },
        inputs={
            "throttle": 0.8,
            "brake": 0.0,
            "clutch": 0.0,
            "handbrake": 0.0,
            "steer": 0.0,
            "drivingLine": 0.0,
            "aiBrakeDelta": 0.0,
        },
        wheels={
            wn: {
                "slipRatio": 0.04,
                "slipAngle": 0.07,
                "combinedSlip": 0.09,
                "rotation_rad_s": 96.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.4,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.03,
            }
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={
            "carOrdinal": 2451,
            "carClass": "A",
            "performanceIndex": 812,
            "numCylinders": 6,
            "carGroup": 18,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": 1,
            "position": 1,
            "currentLapS": 1.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 1.0,
        },
        tail_reserved_byte=0,
    )


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.state.session_repo = InMemorySessionRepository()
    a.state.frame_store = InMemoryFrameStore()
    a.state.coach_repo = InMemoryCoachRepository()
    a.state.lap_repo = InMemoryLapRepository()
    a.state.session_events_repo = InMemorySessionEventsRepository()
    a.include_router(sessions_router, prefix="/api/sessions")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _seed(app: FastAPI, *, session_id: str, car_id: str, lap_count: int = 3) -> Session:
    s = Session(
        id=SessionId(session_id),
        car_id=CarId(car_id),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 17, 11, 30, tzinfo=UTC),
        duration_s=1800.0,
        lap_count=lap_count,
        best_lap_s=68.4,
        closed_reason=SessionCloseReason.SHUTDOWN,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    app.state.car_repo.cars[car_id] = Car(
        id=CarId(car_id),
        display_name=car_id,
        short_name=car_id[:4],
        car_ordinal=2451,
        car_class="A",
        performance_index=812,
        drivetrain="AWD",
        car_group=18,
    )
    return s


def test_list_sessions_filters_and_shape(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a", lap_count=2)
    _seed(app, session_id="s_2", car_id="car_b", lap_count=4)
    r = client.get("/api/sessions")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    for s in body:
        for key in ("id", "carId", "type", "startedAt", "lapCount"):
            assert key in s


def test_list_sessions_by_car(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    _seed(app, session_id="s_2", car_id="car_b")
    r = client.get("/api/sessions?carId=car_a")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["carId"] == "car_a"


def test_list_sessions_cursor_roundtrip(app: FastAPI, client: TestClient) -> None:
    for i in range(5):
        _seed(app, session_id=f"s_{i}", car_id="car_a")
    r1 = client.get("/api/sessions?carId=car_a&limit=2")
    body1 = r1.json()
    assert len(body1) == 2
    next_cursor = r1.headers.get("X-Next-Cursor")
    assert next_cursor is not None
    r2 = client.get(f"/api/sessions?carId=car_a&limit=2&cursor={next_cursor}")
    body2 = r2.json()
    assert len(body2) == 2
    ids1 = {s["id"] for s in body1}
    ids2 = {s["id"] for s in body2}
    assert ids1.isdisjoint(ids2)


def test_list_sessions_no_next_cursor_on_last_page(app: FastAPI, client: TestClient) -> None:
    for i in range(3):
        _seed(app, session_id=f"s_{i}", car_id="car_a")
    r = client.get("/api/sessions?carId=car_a&limit=10")
    assert r.status_code == 200
    assert len(r.json()) == 3
    assert "X-Next-Cursor" not in r.headers


def test_session_detail_404(client: TestClient) -> None:
    r = client.get("/api/sessions/s_unknown")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


def test_session_detail_shape(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a", lap_count=2)
    r = client.get("/api/sessions/s_1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "s_1"
    assert body["carId"] == "car_a"
    assert body["lapCount"] == 2
    assert "lapRollups" in body and isinstance(body["lapRollups"], list)
    assert "timeline10hz" in body
    assert "callouts" in body
    assert "events" in body and isinstance(body["events"], list)
    assert len(body["lapRollups"]) == 2  # one rollup per lap (MVP)


def test_session_detail_returns_persisted_events(app: FastAPI, client: TestClient) -> None:
    """SessionDetail surfaces the historical event log from
    `session_events_repo` ordered by `atS`. Verifies #15 — the highlight-
    reel sink wired through to the API."""
    _seed(app, session_id="s_events", car_id="car_a", lap_count=1)
    events_repo: InMemorySessionEventsRepository = app.state.session_events_repo
    # save_many on the in-memory fake is purely additive — we can call
    # the underlying dict directly to avoid running a coroutine outside
    # the async-test loop.
    events_repo._by_session.setdefault("s_events", []).extend(
        [
            SessionEvent(
                session_id="s_events",
                at_s=12.5,
                kind="oversteer",
                payload={"frontSlip": 0.1, "rearSlip": 0.25},
            ),
            SessionEvent(
                session_id="s_events",
                at_s=3.0,
                kind="lap_completed",
                payload={"lap": 0, "lastLapS": 68.4},
            ),
            SessionEvent(
                session_id="s_events",
                at_s=42.1,
                kind="off_track",
            ),
        ]
    )
    r = client.get("/api/sessions/s_events")
    assert r.status_code == 200
    events = r.json()["events"]
    assert [e["kind"] for e in events] == ["lap_completed", "oversteer", "off_track"]
    assert events[0]["atS"] == 3.0
    assert events[1]["payload"]["frontSlip"] == 0.1
    assert events[2]["payload"] == {}


def test_session_frames_projection(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    sm = SessionManager(silence_seconds=60.0)
    base = datetime(2026, 5, 17, 11, 0, tzinfo=UTC)
    # Override SessionManager so frames inherit the seeded session id.
    from fh6.domain.entities.session import Session as SE
    from fh6.domain.entities.session import SessionType as ST

    sm._current = SE(
        id=SessionId("s_1"),
        car_id=CarId("car_a"),
        type=ST.RACE,
        started_at=base,
    )
    sm._last_frame_at = base
    import asyncio

    async def _seed_frames() -> None:
        for i in range(60):
            raw = _raw(ts_ms=1000 + i * 1000, x=float(i))
            _decision, frame = attach_session(sm, raw, base + timedelta(seconds=i))
            derivations.apply(frame, [])
            modeled_placeholder.apply_placeholder(frame)
            frame.session_id = SessionId("s_1")
            await app.state.frame_store.append(frame)

    asyncio.run(_seed_frames())

    r = client.get("/api/sessions/s_1/frames?fields=speed,throttle&hz=10")
    assert r.status_code == 200
    body = r.json()
    assert body["sessionId"] == "s_1"
    assert body["hz"] == 10
    assert body["fields"] == ["speed", "throttle"]
    assert body["data"]
    for row in body["data"]:
        assert len(row) == 1 + len(body["fields"])  # time + each requested field


def test_supported_fields_includes_widget_redesign_set() -> None:
    """Replay projection must expose the fields LapTimer / GripBudget /
    GMeter / TireHeatmap read from `frame.*` so they follow the scrubber."""
    from fh6.application.use_cases.get_session_frames import SUPPORTED_FIELDS

    for f in (
        "currentLapS",
        "lastLapS",
        "bestLapS",
        "gripBudget",
        "acceleration",
        "tireTemp",
    ):
        assert f in SUPPORTED_FIELDS, f"missing supported field: {f}"


def test_session_frames_projection_widget_redesign_fields(app: FastAPI, client: TestClient) -> None:
    """End-to-end: request the new fields and confirm shape/echo."""
    _seed(app, session_id="s_1", car_id="car_a")
    sm = SessionManager(silence_seconds=60.0)
    base = datetime(2026, 5, 17, 11, 0, tzinfo=UTC)
    from fh6.domain.entities.session import Session as SE
    from fh6.domain.entities.session import SessionType as ST

    sm._current = SE(
        id=SessionId("s_1"),
        car_id=CarId("car_a"),
        type=ST.RACE,
        started_at=base,
    )
    sm._last_frame_at = base
    import asyncio

    async def _seed_frames() -> None:
        for i in range(10):
            raw = _raw(ts_ms=1000 + i * 1000, x=float(i))
            _decision, frame = attach_session(sm, raw, base + timedelta(seconds=i))
            derivations.apply(frame, [])
            modeled_placeholder.apply_placeholder(frame)
            frame.session_id = SessionId("s_1")
            await app.state.frame_store.append(frame)

    asyncio.run(_seed_frames())

    r = client.get(
        "/api/sessions/s_1/frames?fields=currentLapS,gripBudget,acceleration,tireTemp&hz=10"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fields"] == ["currentLapS", "gripBudget", "acceleration", "tireTemp"]
    assert body["data"]
    for row in body["data"]:
        # time + 4 projected fields
        assert len(row) == 5
        # acceleration column is index 3 → 3-vec or None
        accel = row[3]
        assert accel is None or (isinstance(accel, list) and len(accel) == 3)
        # tireTemp column is index 4 → 4-vec or None
        tt = row[4]
        assert tt is None or (isinstance(tt, list) and len(tt) == 4)


def test_session_frames_rejects_bad_hz(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    r = client.get("/api/sessions/s_1/frames?hz=15")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "validation_failed"
    assert "supported" in detail


def test_session_frames_rejects_bad_field(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    r = client.get("/api/sessions/s_1/frames?fields=bogus")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "validation_failed"


def test_delete_session_is_idempotent(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    r1 = client.delete("/api/sessions/s_1")
    assert r1.status_code == 204
    r2 = client.delete("/api/sessions/s_1")
    assert r2.status_code == 204
    r3 = client.delete("/api/sessions/s_unknown")
    assert r3.status_code == 204


def test_patch_session_renames_and_clears_on_whitespace(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")

    # Initial state: no name.
    initial = client.get("/api/sessions/s_1").json()
    assert initial["name"] is None
    assert initial["bookmarked"] is False

    # Rename round-trip.
    r = client.patch("/api/sessions/s_1", json={"name": "  My hot lap  "})
    assert r.status_code == 200
    body = r.json()
    # Trim is applied on the server side.
    assert body["name"] == "My hot lap"
    assert client.get("/api/sessions/s_1").json()["name"] == "My hot lap"

    # Whitespace-only string clears back to null (matches Tauri prototype).
    r = client.patch("/api/sessions/s_1", json={"name": "   "})
    assert r.status_code == 200
    assert r.json()["name"] is None
    assert client.get("/api/sessions/s_1").json()["name"] is None

    # Explicit null also clears.
    client.patch("/api/sessions/s_1", json={"name": "again"})
    r = client.patch("/api/sessions/s_1", json={"name": None})
    assert r.status_code == 200
    assert r.json()["name"] is None


def test_patch_session_404_when_unknown(client: TestClient) -> None:
    r = client.patch("/api/sessions/s_unknown", json={"bookmarked": True})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


def test_patch_bookmark_promotes_session_in_list_order(app: FastAPI, client: TestClient) -> None:
    # Newest first by default.
    s1 = _seed(app, session_id="s_old", car_id="car_a")
    s2 = _seed(app, session_id="s_mid", car_id="car_a")
    s3 = _seed(app, session_id="s_new", car_id="car_a")
    s1.started_at = datetime(2026, 5, 17, 9, 0, tzinfo=UTC)
    s2.started_at = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
    s3.started_at = datetime(2026, 5, 17, 11, 0, tzinfo=UTC)

    before = [s["id"] for s in client.get("/api/sessions").json()]
    assert before == ["s_new", "s_mid", "s_old"]

    # Bookmark the oldest — it should jump to the top despite being oldest.
    r = client.patch("/api/sessions/s_old", json={"bookmarked": True})
    assert r.status_code == 200
    assert r.json()["bookmarked"] is True

    after = [s["id"] for s in client.get("/api/sessions").json()]
    assert after == ["s_old", "s_new", "s_mid"]

    # Unbookmark — back to recency-only ordering.
    client.patch("/api/sessions/s_old", json={"bookmarked": False})
    restored = [s["id"] for s in client.get("/api/sessions").json()]
    assert restored == ["s_new", "s_mid", "s_old"]


def test_delete_all_sessions_requires_confirm_header(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    _seed(app, session_id="s_2", car_id="car_b")

    r = client.delete("/api/sessions")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "confirmation_required"
    # Sessions untouched.
    assert len(client.get("/api/sessions").json()) == 2

    # Wrong header value also rejected.
    r = client.delete("/api/sessions", headers={"X-Confirm-Clear-All": "true"})
    assert r.status_code == 400
    assert len(client.get("/api/sessions").json()) == 2


def test_delete_all_sessions_with_header_empties_table(app: FastAPI, client: TestClient) -> None:
    _seed(app, session_id="s_1", car_id="car_a")
    _seed(app, session_id="s_2", car_id="car_b")

    r = client.delete("/api/sessions", headers={"X-Confirm-Clear-All": "yes"})
    assert r.status_code == 204
    assert client.get("/api/sessions").json() == []
