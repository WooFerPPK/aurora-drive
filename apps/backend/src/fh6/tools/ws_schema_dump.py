"""Dump WebSocket message schemas to stdout as deterministic JSON Schema.

FastAPI's OpenAPI generator only covers the REST surface; WebSocket
message shapes live in `interfaces/rest/schemas/live.py` +
`interfaces/rest/schemas/coach.py` and need their own JSON Schema
artifact so the frontend can generate typed dispatch helpers via
`json-schema-to-typescript`.

The output is a single JSON-Schema document with all message-type
shapes (and their helper types) hoisted into a flat top-level
`definitions` map. The `live` and `coach` keys at the document root
list which definition each channel uses, so the frontend can keep its
discriminated unions per-channel:

    {
      "live":  { "outbound": "...$ref...", "inbound": "...", "error": "...", "udpBindFailed": "..." },
      "coach": { "outbound": "...", "hello": "..." },
      "definitions": { "Frame": {...}, "Hello": {...}, "CoachStatus": {...}, ... }
    }

Hand-written shapes (`error`, `udpBindFailed`) live in `definitions`
alongside the Pydantic-derived ones so refs resolve uniformly.

Usage:

    uv run python -m fh6.tools.ws_schema_dump > packages/contract/ws.schema.json
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import TypeAdapter

from fh6.interfaces.rest.schemas.coach import CalloutMessage, CoachHello
from fh6.interfaces.rest.schemas.live import LiveInbound, LiveOutbound

# Hand-written shapes for the two messages emitted as raw dicts by the
# WS layer (`interfaces/ws/live.py`). Keep these in sync with the
# JSON the live router constructs.
LIVE_ERROR_SCHEMA: dict[str, Any] = {
    "title": "LiveErrorMessage",
    "type": "object",
    "additionalProperties": True,
    "required": ["type", "code"],
    "properties": {
        "type": {"const": "error"},
        "code": {
            "type": "string",
            "enum": [
                "wrong-channel",
                "unknown-topic",
                "unknown-message",
                "unsupported-rate",
            ],
        },
        "message": {"type": "string"},
        "received": {"type": ["string", "null"]},
        "topics": {"type": "array", "items": {"type": "string"}},
        "hz": {"type": ["number", "null"]},
    },
}

UDP_BIND_FAILED_SCHEMA: dict[str, Any] = {
    "title": "UdpBindFailedMessage",
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "message"],
    "properties": {
        "type": {"const": "udp_bind_failed"},
        "message": {"type": "string"},
    },
}


def _hoist(
    schema: dict[str, Any],
    name: str,
    definitions: dict[str, dict[str, Any]],
) -> None:
    """Move ``schema``'s top-level ``$defs`` entries into ``definitions``
    and register the (stripped) schema under ``name``.

    Last-write-wins on key collisions; Pydantic generates stable names
    so collisions between different TypeAdapter dumps are equivalent
    re-definitions of the same model.
    """
    defs = schema.pop("$defs", None) or {}
    for k, v in defs.items():
        definitions[k] = v
    definitions[name] = schema


def build_schema() -> dict[str, Any]:
    definitions: dict[str, dict[str, Any]] = {}

    pydantic_sources: list[tuple[Any, str]] = [
        (LiveOutbound, "LiveOutbound"),
        (LiveInbound, "LiveInbound"),
        (CalloutMessage, "CoachOutbound"),
        (CoachHello, "CoachHello"),
    ]
    for tp, name in pydantic_sources:
        raw = TypeAdapter(tp).json_schema(ref_template="#/definitions/{model}")
        _hoist(raw, name, definitions)

    # Hand-written shapes — also hoisted into definitions so refs are
    # uniform across the document.
    definitions["LiveErrorMessage"] = dict(LIVE_ERROR_SCHEMA)
    definitions["UdpBindFailedMessage"] = dict(UDP_BIND_FAILED_SCHEMA)

    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "fh-racer WebSocket message schemas",
        "live": {
            "outbound": {"$ref": "#/definitions/LiveOutbound"},
            "inbound": {"$ref": "#/definitions/LiveInbound"},
            "error": {"$ref": "#/definitions/LiveErrorMessage"},
            "udpBindFailed": {"$ref": "#/definitions/UdpBindFailedMessage"},
        },
        "coach": {
            "outbound": {"$ref": "#/definitions/CoachOutbound"},
            "hello": {"$ref": "#/definitions/CoachHello"},
        },
        "definitions": dict(sorted(definitions.items())),
    }


def dump(stream: Any = sys.stdout) -> None:
    schema = build_schema()
    json.dump(schema, stream, sort_keys=True, indent=2, ensure_ascii=False)
    stream.write("\n")


if __name__ == "__main__":  # pragma: no cover
    dump()
