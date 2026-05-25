from __future__ import annotations

import sys

import uvicorn

from fh6.infrastructure.config import load_from_env


def main() -> int:
    try:
        config = load_from_env()
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    uvicorn.run(
        "fh6.interfaces.app:create_app",
        factory=True,
        host=config.http_host,
        port=config.http_port,
        log_level=config.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
