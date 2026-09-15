#!/usr/bin/env python3
"""SQL Server attendance bridge entrypoint.

Reads new punches from SQL Server and pushes them to the existing Odoo bridge API.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ.setdefault("SOURCE_TYPE", "sql")

from agent import main

if __name__ == "__main__":
    raise SystemExit(main())
