# -*- coding: utf-8 -*-
"""Attendance bridge agent.

SOURCE_TYPE=zk   -> read from ZK devices via pyzk
SOURCE_TYPE=sql  -> read from SQL Server table (incremental log_id)
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Allow running as: python3 agent.py from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_utils import getenv, getenv_bool, getenv_int
from odoo_client import OdooBridgeClient
from state import SyncState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
_logger = logging.getLogger("bridge_agent")


def _sync_zk(odoo: OdooBridgeClient) -> int:
    from sources.zk_source import ZkAttendanceSource, load_zk_devices

    bridge_token = getenv("BRIDGE_TOKEN", "")
    devices = load_zk_devices(bridge_token)
    failures = 0
    for device in devices:
        source = ZkAttendanceSource(device)
        try:
            batches = source.fetch_batches()
            for batch in batches:
                odoo.push(
                    token=batch["token"],
                    device_identifier=batch["device_identifier"],
                    records=batch["records"],
                    source=source.source_name,
                )
        except Exception as exc:
            failures += 1
            _logger.error(
                "ZK sync failed for %s: %s",
                device.get("identifier"),
                exc,
            )
    return 1 if failures else 0


def _sync_sql(odoo: OdooBridgeClient) -> int:
    from sources.sql_source import SqlAttendanceSource, SqlSourceConfig

    state = SyncState(getenv("STATE_FILE", "state.json"))
    last_log_id = state.load_last_log_id()
    config = SqlSourceConfig.from_env()
    source = SqlAttendanceSource(config, last_log_id=last_log_id)

    try:
        batches = source.fetch_batches()
    except Exception as exc:
        _logger.error("SQL sync failed while reading records: %s", exc)
        return 1

    if not batches:
        _logger.info("No new attendance records")
        return 0

    new_cursor = None
    try:
        for batch in batches:
            if not batch["records"]:
                continue
            odoo.push(
                token=batch["token"],
                device_identifier=batch["device_identifier"],
                records=batch["records"],
                source=source.source_name,
            )
            if batch.get("cursor") is not None:
                new_cursor = batch["cursor"]
    except Exception as exc:
        _logger.error("Odoo request failed: %s", exc)
        _logger.error("Cursor was NOT updated (last_log_id stays %s)", last_log_id)
        return 1

    if new_cursor is not None and int(new_cursor) > int(last_log_id):
        state.save_last_log_id(int(new_cursor))
        _logger.info("Updated last_log_id to %s", new_cursor)
    return 0


def run_once() -> int:
    source_type = getenv("SOURCE_TYPE", "zk").strip().lower()
    odoo_url = getenv("ODOO_URL", required=True)
    odoo = OdooBridgeClient(odoo_url)

    if source_type in {"zk", "device", "zkteco"}:
        return _sync_zk(odoo)
    if source_type in {"sql", "sqlserver", "mssql"}:
        return _sync_sql(odoo)
    raise RuntimeError(f"Unsupported SOURCE_TYPE={source_type!r}. Use 'zk' or 'sql'.")


def main() -> int:
    run_once_mode = getenv_bool("RUN_ONCE", "0")
    sync_interval = getenv_int("SYNC_INTERVAL", "60")

    if run_once_mode:
        try:
            return run_once()
        except Exception as exc:
            _logger.error("Bridge sync failed: %s", exc)
            return 1

    try:
        while True:
            try:
                exit_code = run_once()
                if exit_code != 0:
                    _logger.error("Sync cycle finished with exit code %s", exit_code)
            except Exception as exc:
                _logger.error("Bridge sync failed: %s", exc)

            _logger.info("Waiting %s seconds before next sync...", sync_interval)
            time.sleep(sync_interval)
    except KeyboardInterrupt:
        _logger.info("Stopped by user")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
