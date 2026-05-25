"""Prompt template loader. Templates are plain text with `{{placeholder}}` syntax."""

from __future__ import annotations

import re
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent
_PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def load_template(name: str) -> str:
    path = _TEMPLATES_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def render(template: str, context: dict[str, object]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"missing template var: {key!r}")
        return str(context[key])

    return _PLACEHOLDER_RE.sub(repl, template)
