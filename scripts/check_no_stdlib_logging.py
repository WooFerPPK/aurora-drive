"""Pre-commit hook: forbid stdlib `logging` in production backend code.

Production code uses structlog via `fh6.infrastructure.logging.get_logger`.
The two legitimate consumers of stdlib `logging` are excluded by the
hook's `exclude:` regex in `.pre-commit-config.yaml`:

  - fh6.infrastructure.logging (the wrapper module itself)
  - fh6.infrastructure.db.migrations.env (Alembic's required pattern)

Exits non-zero with a list of offending files when stdlib logging is
imported. Sub-PR 2h sweeps the remaining offenders surfaced by
`pre-commit run --all-files`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PATTERN = re.compile(r"^\s*(import logging\b|from logging\b)")


def main(argv: list[str]) -> int:
    offenders: list[str] = []
    for arg in argv:
        path = Path(arg)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"could not read {arg}: {exc}", file=sys.stderr)
            return 2
        if any(_PATTERN.match(line) for line in content.splitlines()):
            offenders.append(arg)
    if offenders:
        print("stdlib logging is forbidden; use structlog via fh6.infrastructure.logging.")
        for f in offenders:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
