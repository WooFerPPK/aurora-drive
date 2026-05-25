#!/bin/bash
# Source .env from this script's directory and launch the backend.
set -a
HERE="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE/.env" ] && . "$HERE/.env"
set +a
exec uv run python -m fh6.main
