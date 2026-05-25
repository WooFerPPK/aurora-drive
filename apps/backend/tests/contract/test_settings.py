"""T162: contract test for `/api/settings` (API spec §10 + Q2)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.infrastructure.db.repositories.settings import DEFAULT_SETTINGS
from fh6.interfaces.rest.settings_router import router as settings_router


class _InMemorySettings:
    def __init__(self) -> None:
        self._all: dict = {
            k: (list(v) if isinstance(v, list) else dict(v)) for k, v in DEFAULT_SETTINGS.items()
        }

    async def get_all(self) -> dict[str, dict]:
        return self._all

    async def get_group(self, key: str) -> dict:
        return dict(self._all.get(key, {}))

    async def patch(self, partial: dict[str, dict]) -> dict[str, dict]:
        for k, v in partial.items():
            if isinstance(v, dict):
                self._all[k] = {**self._all.get(k, {}), **v}
            else:
                self._all[k] = v  # type: ignore[assignment]
        return self._all


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.settings_repo = _InMemorySettings()
    a.include_router(settings_router, prefix="/api/settings")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_default_settings_pinned(client: TestClient) -> None:
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["telemetry"]["listenAddr"] == "127.0.0.1"
    assert body["telemetry"]["listenPort"] == 5302
    assert body["data"]["shareAnalytics"] is False  # constitution Principle II
    assert body["data"]["maxBytesPerCar"] == 5_368_709_120  # Q2 default


def test_patch_happy_path(client: TestClient) -> None:
    r = client.patch(
        "/api/settings",
        json={
            "display": {"theme": "light", "speedUnit": "mph", "tempUnit": "f", "reduceMotion": True}
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["display"]["theme"] == "light"


def test_patch_rejects_forbidden_port(client: TestClient) -> None:
    r = client.patch(
        "/api/settings",
        json={
            "telemetry": {
                "listenAddr": "127.0.0.1",
                "listenPort": 5250,
                "gameProfile": "fh6",
                "autoDetectCadence": True,
                "preferredFrameRate": 30,
            }
        },
    )
    # The Pydantic field validator fires first → 422.
    # Either 400 (router-level validation) or 422 (model-level) is acceptable,
    # both surface a documented error body.
    assert r.status_code in (400, 422)


def test_patch_rejects_sub_floor_max_bytes(client: TestClient) -> None:
    r = client.patch(
        "/api/settings",
        json={
            "data": {
                "recordSessions": True,
                "storeRawPackets": False,
                "retentionDays": 90,
                "shareAnalytics": False,
                "maxBytesPerCar": 1_000_000,
            }
        },
    )
    assert r.status_code in (400, 422)


def test_world_map_calibration_round_trip(client: TestClient) -> None:
    # Default calibration is the fh6-tel Japan preset; lets the world_map
    # widget render correctly against the bundled tiles before users run
    # their own calibration on real FH6 maps.
    body = client.get("/api/settings").json()
    cal = body["worldMap"]["calibration"]
    assert cal is not None
    assert len(cal["aWorld"]) == 2 and len(cal["aPix"]) == 2
    assert len(cal["bWorld"]) == 2 and len(cal["bPix"]) == 2

    new = {
        "aWorld": [100.0, 200.0],
        "aPix": [1000.0, 2000.0],
        "bWorld": [5000.0, -3000.0],
        "bPix": [9000.0, 4000.0],
    }
    r = client.patch("/api/settings", json={"worldMap": {"calibration": new}})
    assert r.status_code == 200
    assert r.json()["worldMap"]["calibration"] == new


def test_world_map_calibration_rejects_short_pairs(client: TestClient) -> None:
    # Each calibration point is exactly 2 floats. Pydantic enforces the
    # length so half-set or rotation-extended forms can't be persisted.
    r = client.patch(
        "/api/settings",
        json={
            "worldMap": {
                "calibration": {
                    "aWorld": [1.0],
                    "aPix": [2.0, 3.0],
                    "bWorld": [4.0, 5.0],
                    "bPix": [6.0, 7.0],
                }
            }
        },
    )
    assert r.status_code in (400, 422)


def test_world_map_calibration_rejects_coincident_x(client: TestClient) -> None:
    # aWorld and bWorld share the same X — the per-axis linear transform
    # would divide by zero on the X axis.
    r = client.patch(
        "/api/settings",
        json={
            "worldMap": {
                "calibration": {
                    "aWorld": [100.0, 200.0],
                    "aPix": [1000.0, 2000.0],
                    "bWorld": [100.0, 500.0],
                    "bPix": [3000.0, 4000.0],
                }
            }
        },
    )
    assert r.status_code in (400, 422)


def test_world_map_calibration_rejects_coincident_z(client: TestClient) -> None:
    # aWorld and bWorld share the same Z — Z-axis transform would
    # divide by zero.
    r = client.patch(
        "/api/settings",
        json={
            "worldMap": {
                "calibration": {
                    "aWorld": [100.0, 200.0],
                    "aPix": [1000.0, 2000.0],
                    "bWorld": [500.0, 200.0],
                    "bPix": [3000.0, 4000.0],
                }
            }
        },
    )
    assert r.status_code in (400, 422)
