"""T072: contract test for `/api/cars` (API spec §4)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.domain.entities.car import Car
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.cars_router import data_router
from fh6.interfaces.rest.cars_router import router as cars_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    session_repo = InMemorySessionRepository()
    a.state.car_repo = InMemoryCarRepository(session_repo=session_repo)
    a.state.session_repo = session_repo
    a.state.frame_store = InMemoryFrameStore()
    a.include_router(cars_router, prefix="/api/cars")
    a.include_router(data_router, prefix="/api/data")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_car(app: FastAPI) -> Car:
    car = Car(
        id=CarId("car_2451_812"),
        display_name="Lamborghini Aventador SVJ",
        short_name="svj",
        car_ordinal=2451,
        car_class="A",
        performance_index=812,
        drivetrain="AWD",
        car_group=18,
        car_group_label="Hyper Cars",  # FR-020
        last_seen_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
        session_count=3,
        total_seconds_driven=1234.5,
    )
    repo: InMemoryCarRepository = app.state.car_repo
    repo.cars[str(car.id)] = car
    return car


def _seed_session(
    app: FastAPI,
    car_id: CarId,
    *,
    session_id: str,
    closed: bool = True,
    started_at: datetime | None = None,
    lap_count: int = 3,
    best_lap: float = 68.4,
) -> Session:
    s = Session(
        id=SessionId(session_id),
        car_id=car_id,
        type=SessionType.RACE,
        started_at=started_at or datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
        ended_at=(datetime(2026, 5, 17, 11, 30, tzinfo=UTC) if closed else None),
        duration_s=1800.0 if closed else None,
        lap_count=lap_count,
        best_lap_s=best_lap,
        closed_reason=SessionCloseReason.SHUTDOWN if closed else None,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    return s


def test_list_cars_returns_group_label_FR_020(client: TestClient, seeded_car: Car) -> None:
    r = client.get("/api/cars")
    assert r.status_code == 200
    body = r.json()
    assert "cars" in body
    assert len(body["cars"]) == 1
    car = body["cars"][0]
    assert car["id"] == str(seeded_car.id)
    assert car["display"] == seeded_car.display_name
    # FR-020 car group label.
    assert car["groupLabel"] == "Hyper Cars"
    # FH spec §4 fields present.
    for key in ("ordinal", "pi", "drivetrain", "group", "sessionCount", "totalSecondsDriven"):
        assert key in car


def test_car_aggregate_shape(client: TestClient, seeded_car: Car, app: FastAPI) -> None:
    _seed_session(app, seeded_car.id, session_id="s_1", lap_count=4, best_lap=68.1)
    _seed_session(app, seeded_car.id, session_id="s_2", lap_count=3, best_lap=70.0)
    r = client.get(f"/api/cars/{seeded_car.id}/aggregate")
    assert r.status_code == 200
    body = r.json()
    assert body["carId"] == str(seeded_car.id)
    assert body["lapsTotal"] == 7
    assert body["gripBudgetCeiling"] >= 0.0
    # Required fields per API spec §4.
    for key in (
        "sectorBests",
        "perCornerAverages",
        "shift",
        "tirePeakUseByCorner",
        "preferredGearByCorner",
        "thisCarSpecificStyle",
    ):
        assert key in body


def test_car_aggregate_404_on_unknown(client: TestClient) -> None:
    r = client.get("/api/cars/car_unknown/aggregate")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


def test_delete_car_sessions_is_idempotent(client: TestClient, seeded_car: Car) -> None:
    r1 = client.delete(f"/api/cars/{seeded_car.id}/sessions")
    assert r1.status_code == 204
    r2 = client.delete(f"/api/cars/{seeded_car.id}/sessions")
    assert r2.status_code == 204
    # Even unknown id is 204 (idempotent per spec).
    r3 = client.delete("/api/cars/car_does_not_exist/sessions")
    assert r3.status_code == 204


def test_delete_all_data_requires_confirm_header(client: TestClient) -> None:
    r_no = client.delete("/api/data/all")
    assert r_no.status_code == 400
    assert r_no.json()["detail"]["error"] == "confirmation_required"

    r_yes = client.delete("/api/data/all", headers={"X-Confirm": "true"})
    assert r_yes.status_code == 204


def test_delete_car_cascades_sessions(client: TestClient, seeded_car: Car, app: FastAPI) -> None:
    _seed_session(app, seeded_car.id, session_id="s_1")
    _seed_session(app, seeded_car.id, session_id="s_2", closed=False)

    r = client.delete(f"/api/cars/{seeded_car.id}")
    assert r.status_code == 204

    # Car gone from the list (dropdown will be empty).
    listing = client.get("/api/cars").json()
    assert listing["cars"] == []
    # Sessions cascaded.
    assert app.state.session_repo.sessions == {}


def test_delete_car_is_idempotent(client: TestClient) -> None:
    r1 = client.delete("/api/cars/car_does_not_exist")
    assert r1.status_code == 204


def test_delete_all_data_wipes_cars_too(client: TestClient, seeded_car: Car, app: FastAPI) -> None:
    _seed_session(app, seeded_car.id, session_id="s_1")

    r = client.delete("/api/data/all", headers={"X-Confirm": "true"})
    assert r.status_code == 204

    listing = client.get("/api/cars").json()
    assert listing["cars"] == []
    assert app.state.session_repo.sessions == {}


def test_patch_car_by_ordinal_renames_and_round_trips(client: TestClient, seeded_car: Car) -> None:
    # Crowdsource a corrected name for an ordinal the static lookup
    # doesn't cover; the stamped name must survive a subsequent GET.
    r = client.patch(
        f"/api/cars/{seeded_car.car_ordinal}",
        json={"displayName": "Lamborghini Huracán Tecnica"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ordinal"] == seeded_car.car_ordinal
    assert body["displayName"] == "Lamborghini Huracán Tecnica"
    assert body["shortName"] == "Huracán Tecnica"
    assert body["updated"] == 1

    listing = client.get("/api/cars").json()
    target = next(c for c in listing["cars"] if c["ordinal"] == seeded_car.car_ordinal)
    assert target["display"] == "Lamborghini Huracán Tecnica"
    assert target["short"] == "Huracán Tecnica"


def test_patch_car_by_ordinal_accepts_snake_case_alias(client: TestClient, seeded_car: Car) -> None:
    # WireModel allows both alias (camelCase) and field name (snake_case).
    r = client.patch(
        f"/api/cars/{seeded_car.car_ordinal}",
        json={"display_name": "Aventador SVJ"},
    )
    assert r.status_code == 200
    assert r.json()["displayName"] == "Aventador SVJ"


def test_patch_car_by_unknown_ordinal_returns_404(client: TestClient) -> None:
    r = client.patch("/api/cars/999999", json={"displayName": "Phantom"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


def test_patch_car_rejects_empty_name(client: TestClient, seeded_car: Car) -> None:
    r = client.patch(f"/api/cars/{seeded_car.car_ordinal}", json={"displayName": ""})
    # Pydantic min_length=1 surfaces as 422.
    assert r.status_code == 422
