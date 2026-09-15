# -*- coding: utf-8 -*-
"""Persistent sync cursor for incremental SQL attendance import."""

from __future__ import annotations

import json
import os
from pathlib import Path


class SyncState:
    def __init__(self, path: str):
        self.path = Path(path)

    def load_last_log_id(self) -> int:
        if not self.path.exists():
            return 0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        value = data.get("last_log_id", 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def save_last_log_id(self, last_log_id: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"last_log_id": int(last_log_id)}
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_path, self.path)
