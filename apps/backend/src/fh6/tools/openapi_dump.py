"""Dump the FastAPI OpenAPI schema to stdout as deterministic JSON.

Used by `make codegen` (and `make codegen.check` in CI) to keep
`packages/contract/openapi.json` in sync with the live FastAPI app.

Usage:

    uv run python -m fh6.tools.openapi_dump > packages/contract/openapi.json

The output is sorted-keys and `\\n`-terminated so diffs are stable across
machines. The app is constructed via the normal `create_app()` path so
the schema reflects exactly what mounts in production.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from fh6.interfaces.app import create_app


async def _build_schema() -> dict[str, Any]:
    # Wrapped in asyncio.run so any `asyncio.Queue()` constructed during
    # `build_infrastructure` has a running event loop to bind to.
    app = create_app()
    return app.openapi()


def dump(stream: Any = sys.stdout) -> None:
    schema = asyncio.run(_build_schema())
    json.dump(schema, stream, sort_keys=True, indent=2, ensure_ascii=False)
    stream.write("\n")


if __name__ == "__main__":  # pragma: no cover
    dump()
