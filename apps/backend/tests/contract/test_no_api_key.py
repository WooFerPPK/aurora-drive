"""Constitution Principle III + FR-029: no Anthropic API key anywhere
in repo or process env, and no SDK import in any source file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_FORBIDDEN_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "ANTHROPIC_KEY",
}

# Substring patterns. We scan repo files for any of these.
_FORBIDDEN_PATTERNS = (
    re.compile(r"\bANTHROPIC_API_KEY\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"from\s+anthropic\b"),
    re.compile(r"import\s+anthropic\b"),
)

_SCAN_SUFFIXES = {
    ".py",
    ".env",
    ".env.example",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".sh",
    ".ps1",
    ".json",
    ".txt",
}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "build",
    "dist",
    ".specify",
    ".claude",
    ".worktrees",
    # The two reference markdowns + this test itself are allowed to mention the key by name.
}

_THIS_FILE = Path(__file__).resolve()


def _scan_iter():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(p in _SKIP_DIRS for p in path.parts):
            continue
        if path == _THIS_FILE:
            continue
        if path.suffix not in _SCAN_SUFFIXES and path.name not in {".env.example"}:
            continue
        yield path


def test_no_anthropic_api_key_in_env() -> None:
    leaks = [k for k in _FORBIDDEN_ENV_KEYS if os.environ.get(k)]
    assert not leaks, f"forbidden env var(s) set in test environment: {leaks}"


def test_no_anthropic_api_key_in_repo_files() -> None:
    offenders: list[tuple[str, str]] = []
    for path in _scan_iter():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in _FORBIDDEN_PATTERNS:
            if pat.search(text):
                offenders.append((str(path.relative_to(REPO_ROOT)), pat.pattern))
    assert not offenders, (
        "constitution Principle III violation — forbidden patterns found: "
        + ", ".join(f"{p}:{pat}" for p, pat in offenders)
    )
