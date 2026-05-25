"""T165: contract tests for `/api/layouts` (API spec §11)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.interfaces.rest.layouts_router import router as layouts_router
from fh6.interfaces.rest.widget_kinds import KINDS as CATALOG_KINDS


class _InMemoryLayouts:
    def __init__(self) -> None:
        self._by_page: dict[str, dict] = {}

    async def get(self, page_id: str):
        return self._by_page.get(page_id)

    async def put(self, page_id: str, layout: dict) -> None:
        self._by_page[page_id] = layout

    async def patch(self, page_id: str, partial: dict) -> dict:
        cur = self._by_page.get(page_id, {})
        merged = {**cur, **partial}
        self._by_page[page_id] = merged
        return merged


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.layouts_repo = _InMemoryLayouts()
    a.include_router(layouts_router, prefix="/api/layouts")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_put_then_get_roundtrips(client: TestClient) -> None:
    body = {
        "name": "my live",
        "grid": {"cols": 12, "rowHeight": 40},
        "widgets": [
            {"id": "w1", "kind": "speed_dial", "x": 0, "y": 0, "w": 3, "h": 3, "props": {}},
            {"id": "w2", "kind": "tire_heatmap", "x": 3, "y": 0, "w": 3, "h": 3, "props": {}},
        ],
    }
    r_put = client.put("/api/layouts/live", json=body)
    assert r_put.status_code == 200
    r_get = client.get("/api/layouts/live")
    assert r_get.status_code == 200
    got = r_get.json()
    assert got["pageId"] == "live"
    assert got["widgets"][0]["kind"] == "speed_dial"


def test_put_rejects_unknown_widget_kind(client: TestClient) -> None:
    body = {
        "name": "",
        "grid": {"cols": 12, "rowHeight": 40},
        "widgets": [
            {"id": "w1", "kind": "bogus_widget", "x": 0, "y": 0, "w": 3, "h": 3, "props": {}}
        ],
    }
    r = client.put("/api/layouts/live", json=body)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "validation_failed"
    assert "supported" in detail


def test_unknown_page_id_rejected(client: TestClient) -> None:
    r = client.get("/api/layouts/ghost")
    assert r.status_code == 400


def test_catalog_cross_reference_invariant(client: TestClient) -> None:
    # Every widget kind in the backend's KINDS allow-list must be
    # acceptable in a layout PUT. The catalog endpoint itself was
    # deleted in Phase 3 (§1.3 #6) — the frontend's `widgetRegistry`
    # is now the only catalog; the backend just validates the
    # allow-list when persisting layouts.
    body = {
        "name": "",
        "grid": {"cols": 12, "rowHeight": 40},
        "widgets": [
            {"id": f"w{i}", "kind": k, "x": i, "y": 0, "w": 1, "h": 1, "props": {}}
            for i, k in enumerate(sorted(CATALOG_KINDS))
        ],
    }
    r_put = client.put("/api/layouts/customize", json=body)
    assert r_put.status_code == 200


def test_patch_partial_merge(client: TestClient) -> None:
    client.put(
        "/api/layouts/live",
        json={
            "name": "first",
            "grid": {"cols": 12, "rowHeight": 40},
            "widgets": [
                {"id": "w1", "kind": "speed_dial", "x": 0, "y": 0, "w": 3, "h": 3, "props": {}}
            ],
        },
    )
    r = client.patch("/api/layouts/live", json={"name": "renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "renamed"
