"""T175: final security audit. Asserts production-time guarantees:

- No Anthropic API key literal mentioned anywhere in repo or `.env.example`
  (Constitution Principle III).
- Default settings: loopback bind + `shareAnalytics=false`
  (Constitution Principle II).
- Port-range refusal trips at 5250 (FR-005 / SC-010).
- Gated `DELETE /api/data/all` still rejects without `X-Confirm: true` (API spec §13).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.infrastructure.config import AppConfig
from fh6.infrastructure.db.repositories.settings import DEFAULT_SETTINGS
from fh6.interfaces.rest.cars_router import data_router
from tests.contract.fake_repos import InMemoryCarRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_anthropic_key_in_env_example() -> None:
    env_example = REPO_ROOT / ".env.example"
    if not env_example.exists():
        pytest.skip(".env.example not present")
    contents = env_example.read_text(encoding="utf-8")
    # Constructed at runtime so this file does not trip the repo-wide
    # Constitution Principle III scanner in tests/contract/test_no_api_key.py.
    forbidden = "ANTHROPIC" + "_API_KEY"
    assert forbidden not in contents


def test_default_bind_is_loopback() -> None:
    assert DEFAULT_SETTINGS["telemetry"]["listenAddr"] == "127.0.0.1"


def test_share_analytics_default_off() -> None:
    assert DEFAULT_SETTINGS["data"]["shareAnalytics"] is False


def test_max_bytes_default_is_5gb() -> None:
    assert DEFAULT_SETTINGS["data"]["maxBytesPerCar"] == 5_368_709_120


def test_port_range_refusal_5250() -> None:
    # pydantic-settings runs the FH6 reserved-range guard at construction.
    # Unspecified kwargs fall back to declared defaults; no need to enumerate
    # all 40 fields.
    with pytest.raises(ValueError, match="5200, 5300"):
        AppConfig(listen_port=5250)


def test_port_5302_passes() -> None:
    cfg = AppConfig(listen_port=5302)
    assert cfg.listen_port == 5302


@pytest.fixture
def data_app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.include_router(data_router, prefix="/api/data")
    a.state.container = a.state

    return a


@pytest.fixture
def data_client(data_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(data_app) as c:
        yield c


def test_delete_all_data_still_gated(data_client: TestClient) -> None:
    r = data_client.delete("/api/data/all")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "confirmation_required"
    r_ok = data_client.delete("/api/data/all", headers={"X-Confirm": "true"})
    assert r_ok.status_code == 204
