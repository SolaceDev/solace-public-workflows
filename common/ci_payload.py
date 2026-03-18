#!/usr/bin/env python3
"""Shared helpers for CI payload construction and parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def to_bool(raw: str | None, default: bool = False) -> bool:
    """Convert common CI string booleans to Python bool."""
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def safe_int(raw: Any, default: int = 0) -> int:
    """Convert values to int safely."""
    try:
        return int(raw or 0)
    except Exception:
        return default


def read_json_file(path: str | Path, default: Any | None = None) -> Any:
    """Read JSON from file and return a default value on parse/read errors."""
    resolved = Path(path)
    if not resolved.exists():
        return {} if default is None else default
    try:
        return json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default
