"""T163: `/api/layouts/:pageId` (API spec §11)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from fh6.interfaces.dependencies import LayoutsRepoDep
from fh6.interfaces.rest.errors import validation_error_400
from fh6.interfaces.rest.schemas.layouts import (
    GridConfig,
    LayoutPatchBody,
    LayoutPutBody,
    LayoutResponse,
    WidgetInstance,
)
from fh6.interfaces.rest.widget_kinds import KINDS as CATALOG_KINDS

router = APIRouter()

SUPPORTED_PAGES: frozenset[str] = frozenset(
    {
        "live",
        "sessions",
        "coach",
        "predictions",
        "driver",
        "track",
        "customize",
        "settings",
    }
)


def _validate_widgets(widgets: list[WidgetInstance]) -> None:
    for w in widgets:
        if w.kind not in CATALOG_KINDS:
            raise validation_error_400(
                f"unknown widget kind {w.kind!r}",
                field="widgets.kind",
                supported=sorted(CATALOG_KINDS),
            )


@router.get("/{page_id}", response_model=LayoutResponse)
async def get_layout(page_id: str, layouts_repo: LayoutsRepoDep) -> LayoutResponse:
    if page_id not in SUPPORTED_PAGES:
        raise validation_error_400(
            f"unknown pageId {page_id!r}",
            field="pageId",
            supported=sorted(SUPPORTED_PAGES),
        )
    payload = await layouts_repo.get(page_id)
    if payload is None:
        return LayoutResponse(pageId=page_id)
    return LayoutResponse(
        pageId=page_id,
        name=payload.get("name", ""),
        grid=GridConfig(**payload.get("grid", {})),
        widgets=[WidgetInstance(**w) for w in payload.get("widgets", [])],
        updatedAt=payload.get("updatedAt"),
    )


@router.put("/{page_id}", response_model=LayoutResponse)
async def put_layout(
    page_id: str,
    body: LayoutPutBody,
    layouts_repo: LayoutsRepoDep,
) -> LayoutResponse:
    if page_id not in SUPPORTED_PAGES:
        raise validation_error_400(
            f"unknown pageId {page_id!r}",
            field="pageId",
            supported=sorted(SUPPORTED_PAGES),
        )
    _validate_widgets(body.widgets)
    now = datetime.now(UTC).isoformat()
    payload = {
        "name": body.name,
        "grid": body.grid.model_dump(),
        "widgets": [w.model_dump() for w in body.widgets],
        "updatedAt": now,
    }
    await layouts_repo.put(page_id, payload)
    return LayoutResponse(
        pageId=page_id,
        name=body.name,
        grid=body.grid,
        widgets=body.widgets,
        updatedAt=now,
    )


@router.patch("/{page_id}", response_model=LayoutResponse)
async def patch_layout(
    page_id: str,
    body: LayoutPatchBody,
    layouts_repo: LayoutsRepoDep,
) -> LayoutResponse:
    if page_id not in SUPPORTED_PAGES:
        raise validation_error_400(
            f"unknown pageId {page_id!r}",
            field="pageId",
            supported=sorted(SUPPORTED_PAGES),
        )
    if body.widgets is not None:
        _validate_widgets(body.widgets)
    partial: dict[str, object] = {}
    if body.name is not None:
        partial["name"] = body.name
    if body.grid is not None:
        partial["grid"] = body.grid.model_dump()
    if body.widgets is not None:
        partial["widgets"] = [w.model_dump() for w in body.widgets]
    partial["updatedAt"] = datetime.now(UTC).isoformat()
    merged = await layouts_repo.patch(page_id, partial)
    return LayoutResponse(
        pageId=page_id,
        name=merged.get("name", ""),
        grid=GridConfig(**merged.get("grid", {})),
        widgets=[WidgetInstance(**w) for w in merged.get("widgets", [])],
        updatedAt=merged.get("updatedAt"),
    )
