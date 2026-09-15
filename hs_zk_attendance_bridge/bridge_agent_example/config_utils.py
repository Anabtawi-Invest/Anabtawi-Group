# -*- coding: utf-8 -*-
"""Shared configuration helpers for the bridge agent."""

from __future__ import annotations

import json
import os


def getenv(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value if value is not None else ""


def getenv_bool(name: str, default: str = "0") -> bool:
    return getenv(name, default).strip().lower() in {"1", "true", "yes"}


def getenv_int(name: str, default: str) -> int:
    return int(getenv(name, default))


def load_json_env(name: str, default: str = "{}") -> dict:
    raw = getenv(name, default).strip() or default
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    return parsed
