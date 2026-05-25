"""Pydantic wire models for `/api/layouts` (API spec §11).

`WidgetCatalogEntry` + `WidgetsCatalogResponse` were removed when the
widget catalog endpoint was deleted (Phase 3, §1.3 #6) — the catalog is
a frontend concern. Backend layout validation uses the bare
`fh6.interfaces.rest.widget_kinds.KINDS` allow-list instead.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class GridConfig(WireModel):
    cols: int = 12
    rowHeight: int = 40


class WidgetInstance(WireModel):
    id: str
    kind: str
    x: int
    y: int
    w: int
    h: int
    props: dict[str, Any] = Field(default_factory=dict)


class LayoutResponse(WireModel):
    pageId: str
    name: str = ""
    grid: GridConfig = Field(default_factory=GridConfig)
    widgets: list[WidgetInstance] = Field(default_factory=list)
    updatedAt: str | None = None


class LayoutPutBody(WireModel):
    name: str = ""
    grid: GridConfig = Field(default_factory=GridConfig)
    widgets: list[WidgetInstance]


class LayoutPatchBody(WireModel):
    name: str | None = None
    grid: GridConfig | None = None
    widgets: list[WidgetInstance] | None = None
