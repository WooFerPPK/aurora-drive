"""Smoke tests for the codegen CLIs (`fh6.tools.openapi_dump` +
`fh6.tools.ws_schema_dump`).

We don't snapshot the full output (it churns whenever a route or
schema lands); we assert structural invariants the codegen step
depends on: the dump is JSON, the top-level shape is right, and a
handful of key routes / message kinds make it into the artifact.
"""

from __future__ import annotations

import io
import json
from typing import Any

from fh6.tools import openapi_dump, ws_schema_dump


def _dumped_openapi() -> dict[str, Any]:
    buf = io.StringIO()
    openapi_dump.dump(buf)
    return json.loads(buf.getvalue())


def _dumped_ws_schema() -> dict[str, Any]:
    buf = io.StringIO()
    ws_schema_dump.dump(buf)
    return json.loads(buf.getvalue())


def test_openapi_dump_is_json_with_paths_and_schemas() -> None:
    doc = _dumped_openapi()
    assert "paths" in doc
    assert "components" in doc and "schemas" in doc["components"]
    assert len(doc["paths"]) >= 30, f"expected >=30 mounted routes; got {len(doc['paths'])}"


def test_openapi_dump_includes_core_routes() -> None:
    doc = _dumped_openapi()
    paths = set(doc["paths"].keys())
    for expected in (
        "/api/cars",
        "/api/sessions",
        "/api/sessions/current",
        "/api/predict/lap",
        "/api/predict/shift",
        "/api/coach/status",
        "/api/settings",
        "/api/layouts/{page_id}",
        "/health/telemetry",
    ):
        assert expected in paths, f"missing route {expected!r} in openapi dump"


def test_openapi_dump_is_deterministic() -> None:
    a = _dumped_openapi()
    b = _dumped_openapi()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _resolve_ref(doc: dict[str, Any], ref: str) -> dict[str, Any]:
    """Tiny `$ref` resolver — only the `#/definitions/...` form ws_schema_dump emits."""
    prefix = "#/definitions/"
    assert ref.startswith(prefix), f"unexpected $ref form: {ref}"
    return doc["definitions"][ref[len(prefix) :]]


def test_ws_schema_dump_groups_by_channel() -> None:
    doc = _dumped_ws_schema()
    assert doc["$schema"].endswith("/schema#")
    assert set(doc["live"].keys()) == {"outbound", "inbound", "error", "udpBindFailed"}
    assert set(doc["coach"].keys()) == {"outbound", "hello"}
    assert "definitions" in doc and len(doc["definitions"]) > 10


def test_ws_schema_live_outbound_covers_all_message_types() -> None:
    doc = _dumped_ws_schema()
    outbound = _resolve_ref(doc, doc["live"]["outbound"]["$ref"])
    # The discriminated union expands as oneOf/anyOf of object-typed
    # schemas each carrying a literal `type` const (sometimes via $ref
    # into definitions).
    variants = outbound.get("oneOf") or outbound.get("anyOf") or []
    types: set[str] = set()
    for v in variants:
        target = _resolve_ref(doc, v["$ref"]) if "$ref" in v else v
        const = target.get("properties", {}).get("type", {}).get("const")
        if const is not None:
            types.add(const)
    assert {"hello", "frame", "frames", "state", "event", "heartbeat"} <= types, (
        f"live outbound union missing message types; got {sorted(types)}"
    )


def test_ws_schema_error_and_udp_bind_failed_present() -> None:
    doc = _dumped_ws_schema()
    err = _resolve_ref(doc, doc["live"]["error"]["$ref"])
    assert err["properties"]["type"]["const"] == "error"
    assert set(err["properties"]["code"]["enum"]) == {
        "wrong-channel",
        "unknown-topic",
        "unknown-message",
        "unsupported-rate",
    }
    bind = _resolve_ref(doc, doc["live"]["udpBindFailed"]["$ref"])
    assert bind["properties"]["type"]["const"] == "udp_bind_failed"


def test_ws_schema_dump_is_deterministic() -> None:
    a = _dumped_ws_schema()
    b = _dumped_ws_schema()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
