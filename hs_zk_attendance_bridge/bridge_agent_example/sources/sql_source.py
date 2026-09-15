# -*- coding: utf-8 -*-
"""SQL Server attendance source with incremental log_id cursor."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config_utils import getenv, getenv_int, load_json_env

_logger = logging.getLogger(__name__)

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise RuntimeError(
            f"Unsafe SQL identifier {name!r}. Use letters, numbers, and underscore only."
        )
    return f"[{name}]"


@dataclass
class SqlSourceConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    table: str
    driver: str
    batch_size: int
    timezone: str
    token: str
    device_identifier: str
    machine_map: dict[str, str]
    start_log_id: int
    encrypt: bool
    trust_server_certificate: bool

    @classmethod
    def from_env(cls) -> "SqlSourceConfig":
        return cls(
            host=getenv("SQL_HOST", required=True),
            port=getenv_int("SQL_PORT", "1433"),
            database=getenv("SQL_DATABASE", required=True),
            user=getenv("SQL_USER", required=True),
            password=getenv("SQL_PASSWORD", required=True),
            table=getenv("SQL_TABLE", "attenendad"),
            driver=getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server"),
            batch_size=getenv_int("BATCH_SIZE", "500"),
            timezone=getenv("DEVICE_TIMEZONE", "Asia/Amman"),
            token=getenv("BRIDGE_TOKEN", required=True),
            device_identifier=getenv("DEVICE_IDENTIFIER", ""),
            machine_map={str(k): str(v) for k, v in load_json_env("MACHINE_MAP", "{}").items()},
            start_log_id=getenv_int("SQL_START_LOG_ID", "0"),
            encrypt=getenv("SQL_ENCRYPT", "yes").strip().lower() in {"1", "true", "yes"},
            trust_server_certificate=getenv("SQL_TRUST_SERVER_CERTIFICATE", "yes")
            .strip()
            .lower()
            in {"1", "true", "yes"},
        )


class SqlAttendanceSource:
    """Reads new rows from SQL Server and normalizes them for the Odoo bridge."""

    source_name = "sql_bridge_agent"

    def __init__(self, config: SqlSourceConfig, last_log_id: int):
        self.config = config
        self.last_log_id = max(int(last_log_id), int(config.start_log_id))

    def _connect(self):
        try:
            import pyodbc
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency pyodbc. Install with: pip install pyodbc"
            ) from exc

        encrypt = "yes" if self.config.encrypt else "no"
        trust = "yes" if self.config.trust_server_certificate else "no"
        conn_str = (
            f"DRIVER={{{self.config.driver}}};"
            f"SERVER={self.config.host},{self.config.port};"
            f"DATABASE={self.config.database};"
            f"UID={self.config.user};"
            f"PWD={self.config.password};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust};"
        )
        return pyodbc.connect(conn_str, timeout=30)

    def _device_identifier(self, machine_id: Any) -> str:
        key = str(machine_id)
        if key in self.config.machine_map:
            return self.config.machine_map[key]
        return f"SQL-ZK-{key}"

    @staticmethod
    def _format_punch_time(value: Any) -> str:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None).isoformat(sep="T", timespec="seconds")
        text = str(value).strip()
        if not text:
            raise ValueError("Empty TrxDateTime")
        # Normalize common SQL Server string formats.
        text = text.replace(" ", "T", 1)
        return text

    def fetch_batches(self) -> list[dict]:
        table_sql = _quote_ident(self.config.table)
        query = f"""
            SELECT TOP (?)
                log_id,
                machine_id,
                empCode,
                TrxType,
                TrxDateTime
            FROM {table_sql}
            WHERE log_id > ?
            ORDER BY TrxDateTime ASC, log_id ASC
        """

        _logger.info("Connecting to SQL Server %s/%s", self.config.host, self.config.database)
        try:
            connection = self._connect()
        except Exception as exc:
            _logger.error("SQL connection failed: %s", exc)
            raise

        rows: list[dict] = []
        try:
            _logger.info("SQL connection successful")
            _logger.info("Last processed log_id: %s", self.last_log_id)
            cursor = connection.cursor()
            cursor.execute(query, self.config.batch_size, self.last_log_id)
            columns = [col[0] for col in cursor.description]
            for raw in cursor.fetchall():
                row = {str(col): value for col, value in zip(columns, raw)}
                rows.append(row)
        finally:
            connection.close()

        _logger.info("Found %s new attendance records", len(rows))
        if not rows:
            return []

        def _get(row: dict, *names: str):
            lowered = {str(k).lower(): v for k, v in row.items()}
            for name in names:
                if name.lower() in lowered:
                    return lowered[name.lower()]
            return None

        # Detect non-monotonic / duplicate log_id before pushing.
        log_ids = []
        for row in rows:
            try:
                log_ids.append(int(_get(row, "log_id")))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid attendance record log_id: {row!r}") from exc

        if len(log_ids) != len(set(log_ids)):
            raise RuntimeError(
                "Duplicate log_id values were returned by SQL. "
                "Incremental sync requires unique log_id values."
            )

        # Keep one chronologically ordered batch so Odoo In/Out pairing stays correct
        # even when punches come from multiple machines.
        records = []
        machine_ids = set()
        max_log_id = self.last_log_id
        for row in rows:
            try:
                log_id = int(_get(row, "log_id"))
                machine_id = _get(row, "machine_id")
                emp_code = _get(row, "empCode", "empcode")
                punch_time = self._format_punch_time(_get(row, "TrxDateTime", "trxdatetime"))
                if emp_code is None or str(emp_code).strip() == "" or str(emp_code).upper() == "NULL":
                    raise ValueError("Missing empCode")
                if machine_id is None or str(machine_id).upper() == "NULL":
                    raise ValueError("Missing machine_id")
            except Exception as exc:
                _logger.error("Invalid attendance record: %s (%s)", row, exc)
                raise RuntimeError(f"Invalid attendance record: {exc}") from exc

            # TrxType is intentionally ignored for Check In / Check Out pairing.
            machine_ids.add(str(machine_id))
            records.append(
                {
                    "device_user_id": str(emp_code).strip(),
                    "punch_time": punch_time,
                    "punch_type": "",
                    "device_timezone": self.config.timezone,
                }
            )
            max_log_id = max(max_log_id, log_id)

        if self.config.device_identifier:
            identifier = self.config.device_identifier
        elif len(machine_ids) == 1:
            identifier = self._device_identifier(next(iter(machine_ids)))
        else:
            identifier = "sql_attendance"

        _logger.info(
            "Prepared %s records from machine_id(s): %s",
            len(records),
            ", ".join(sorted(machine_ids)),
        )
        return [
            {
                "token": self.config.token,
                "device_identifier": identifier,
                "records": records,
                "cursor": max_log_id,
            }
        ]
