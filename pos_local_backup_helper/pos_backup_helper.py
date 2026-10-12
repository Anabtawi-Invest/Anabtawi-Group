#!/usr/bin/env python3
"""Anabtawi POS Local Backup helper.

Runs on the cashier PC, receives POS orders from the Odoo POS (browser) on
127.0.0.1 and stores them in an encrypted SQLite database (SQLCipher).
Also serves a PIN-protected screen showing orders, events and exports.

Commands:
    setup                 interactive first-time configuration (run as Administrator)
    run                   start the service (used by the startup task)
    install-startup       start automatically with Windows (run as Administrator)
    uninstall-startup     remove the startup task
    change-pin            change the manager PIN of the logs screen
    change-db-password    re-encrypt the database with a new password
    show-config           print the API key / allowed origins to enter in Odoo
"""

import argparse
import base64
import csv
import ctypes
import fnmatch
import getpass
import hashlib
import hmac
import html
import io
import json
import logging
import logging.handlers
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError:  # pragma: no cover - only on machines without the wheel
    sqlcipher = None

DB_ERRORS = (sqlite3.Error, sqlcipher.Error) if sqlcipher else (sqlite3.Error,)

APP_NAME = "AnabtawiPOS"
APP_TITLE = "Anabtawi POS Local Backup"
VERSION = "1.2.0"
TASK_NAME = "AnabtawiPOSBackup"
IS_WINDOWS = os.name == "nt"
MAX_BODY_BYTES = 10 * 1024 * 1024
PAGE_SIZE = 50
MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 300

_logger = logging.getLogger("pos_backup")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def data_dir():
    if IS_WINDOWS:
        base = os.environ.get("ProgramData", r"C:\ProgramData")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".anabtawi_pos")


def config_path():
    return os.path.join(data_dir(), "config.json")


def db_path():
    return os.path.join(data_dir(), "pos_backup.db")


def log_dir():
    return os.path.join(data_dir(), "logs")


def setup_logging(to_console=True):
    _logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        os.makedirs(log_dir(), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir(), "helper.log"), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        _logger.addHandler(file_handler)
    except OSError as error:
        # The log file must never prevent the helper from running.
        print(f"Warning: cannot write the log file ({error}); logging to the console only.")
        to_console = True
    if to_console:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        _logger.addHandler(console)


# ---------------------------------------------------------------------------
# Secret protection (Windows DPAPI, machine scope)
# ---------------------------------------------------------------------------

class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _dpapi(data, protect):
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    flags = _CRYPTPROTECT_UI_FORBIDDEN | _CRYPTPROTECT_LOCAL_MACHINE
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), "AnabtawiPOS", None, None, None, flags, ctypes.byref(blob_out)
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, flags, ctypes.byref(blob_out)
        )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect_secret(text):
    raw = text.encode("utf-8")
    if IS_WINDOWS:
        return "dpapi:" + base64.b64encode(_dpapi(raw, protect=True)).decode("ascii")
    # Non-Windows is for development only: the secret is merely encoded.
    return "plain:" + base64.b64encode(raw).decode("ascii")


def unprotect_secret(stored):
    if not stored:
        return ""
    scheme, _, payload = stored.partition(":")
    raw = base64.b64decode(payload)
    if scheme == "dpapi":
        return _dpapi(raw, protect=False).decode("utf-8")
    if scheme == "plain":
        return raw.decode("utf-8")
    raise ValueError("Unknown secret format")


# ---------------------------------------------------------------------------
# PIN hashing
# ---------------------------------------------------------------------------

_PIN_ITERATIONS = 200_000


def hash_pin(pin):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _PIN_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PIN_ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_pin(pin, stored):
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), base64.b64decode(salt_b64), int(iterations)
        )
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "port": 8765,
    "allowed_origins": [],
    "api_key": "",
    "admin_pin_hash": "",
    "db_key": "",
    "session_hours": 8,
    "allow_unencrypted": False,
}


def load_config():
    path = config_path()
    if not os.path.exists(path):
        raise SystemExit(f"No configuration found at {path}. Run the 'setup' command first.")
    with open(path, encoding="utf-8") as handle:
        config = dict(DEFAULT_CONFIG)
        config.update(json.load(handle))
    return config


def save_config(config):
    os.makedirs(data_dir(), exist_ok=True)
    tmp_path = config_path() + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    os.replace(tmp_path, config_path())


def restrict_data_dir():
    """Only Administrators and SYSTEM may read the database, config and logs."""
    if not IS_WINDOWS:
        os.chmod(data_dir(), 0o700)
        return
    # Restrict the folder itself, then make every file inside inherit from it:
    # (OI)(CI) inheritance flags are only valid on folders, never on files.
    subprocess.run(
        [
            "icacls", data_dir(), "/inheritance:r",
            "/grant:r", "*S-1-5-32-544:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F",
        ],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["icacls", os.path.join(data_dir(), "*"), "/reset", "/T", "/C"],
        check=False,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS pos_order (
    uuid TEXT PRIMARY KEY,
    pos_reference TEXT,
    name TEXT,
    config_id INTEGER,
    config_name TEXT,
    session_id INTEGER,
    session_name TEXT,
    date_order TEXT,
    partner_id INTEGER,
    partner_name TEXT,
    cashier TEXT,
    state TEXT,
    amount_total REAL DEFAULT 0,
    amount_tax REAL DEFAULT 0,
    amount_paid REAL DEFAULT 0,
    amount_return REAL DEFAULT 0,
    synced_to_server INTEGER DEFAULT 0,
    server_id INTEGER,
    deleted INTEGER DEFAULT 0,
    deleted_at TEXT,
    payload_json TEXT,
    first_seen TEXT,
    last_update TEXT
);
CREATE INDEX IF NOT EXISTS pos_order_session_idx ON pos_order (session_id);
CREATE INDEX IF NOT EXISTS pos_order_state_idx ON pos_order (state);
CREATE INDEX IF NOT EXISTS pos_order_synced_idx ON pos_order (synced_to_server);

CREATE TABLE IF NOT EXISTS pos_order_line (
    uuid TEXT PRIMARY KEY,
    order_uuid TEXT NOT NULL,
    product_id INTEGER,
    product_name TEXT,
    qty REAL,
    price_unit REAL,
    discount REAL,
    price_subtotal REAL,
    price_subtotal_incl REAL
);
CREATE INDEX IF NOT EXISTS pos_order_line_order_idx ON pos_order_line (order_uuid);

CREATE TABLE IF NOT EXISTS pos_payment (
    uuid TEXT PRIMARY KEY,
    order_uuid TEXT NOT NULL,
    payment_method_id INTEGER,
    payment_method_name TEXT,
    amount REAL,
    payment_date TEXT
);
CREATE INDEX IF NOT EXISTS pos_payment_order_idx ON pos_payment (order_uuid);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    order_uuid TEXT,
    order_ref TEXT,
    message TEXT
);
CREATE INDEX IF NOT EXISTS event_log_ts_idx ON event_log (ts);

CREATE TABLE IF NOT EXISTS pos_advance (
    advance_id INTEGER PRIMARY KEY,
    reference TEXT,
    config_id INTEGER,
    config_name TEXT,
    session_id INTEGER,
    session_name TEXT,
    cashier TEXT,
    partner_name TEXT,
    partner_phone TEXT,
    state TEXT,
    amount_total REAL,
    advance_amount REAL,
    amount_tendered REAL,
    change_amount REAL,
    amount_remaining REAL,
    pledge_amount REAL,
    payment_method_name TEXT,
    created_at TEXT,
    completed_at TEXT,
    completion_order_ref TEXT,
    completion_order_uuid TEXT,
    remaining_paid REAL,
    completion_payment_method TEXT,
    refunded_at TEXT,
    refund_amount REAL,
    refund_payment_method TEXT,
    first_seen TEXT,
    last_update TEXT
);
CREATE INDEX IF NOT EXISTS pos_advance_state_idx ON pos_advance (state);

CREATE TABLE IF NOT EXISTS pos_advance_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    advance_id INTEGER NOT NULL,
    product_id INTEGER,
    product_name TEXT,
    qty REAL,
    price_unit REAL,
    discount REAL,
    subtotal REAL
);
CREATE INDEX IF NOT EXISTS pos_advance_line_advance_idx ON pos_advance_line (advance_id);

CREATE TABLE IF NOT EXISTS pos_event (
    event_uuid TEXT PRIMARY KEY,
    advance_id INTEGER,
    reference TEXT,
    action TEXT NOT NULL,
    ts TEXT,
    received_at TEXT,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS pos_event_advance_idx ON pos_event (advance_id);
CREATE INDEX IF NOT EXISTS pos_event_action_idx ON pos_event (action);

CREATE TABLE IF NOT EXISTS pos_pledge_return (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uuid TEXT UNIQUE,
    ts TEXT,
    config_id INTEGER,
    config_name TEXT,
    session_id INTEGER,
    session_name TEXT,
    cashier TEXT,
    partner_name TEXT,
    partner_phone TEXT,
    payment_method_name TEXT,
    total_amount REAL,
    pledge_count INTEGER,
    refund_orders TEXT,
    origin_orders TEXT,
    return_move_name TEXT
);

CREATE TABLE IF NOT EXISTS pos_pledge_return_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL,
    pledge_id INTEGER,
    reference TEXT,
    product_name TEXT,
    qty REAL,
    amount REAL,
    employee_name TEXT,
    refund_order_name TEXT
);
CREATE INDEX IF NOT EXISTS pos_pledge_return_line_return_idx ON pos_pledge_return_line (return_id);

CREATE TABLE IF NOT EXISTS pos_cash_move (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    move_key TEXT UNIQUE NOT NULL,
    statement_line_id INTEGER,
    ts TEXT,
    config_id INTEGER,
    config_name TEXT,
    session_id INTEGER,
    session_name TEXT,
    move_type TEXT,
    amount REAL,
    reason TEXT,
    name TEXT,
    cashier TEXT,
    source TEXT,
    available_cash REAL,
    queued_offline INTEGER DEFAULT 0,
    deleted INTEGER DEFAULT 0,
    deleted_at TEXT,
    details_json TEXT,
    first_seen TEXT,
    last_update TEXT
);
CREATE INDEX IF NOT EXISTS pos_cash_move_session_idx ON pos_cash_move (session_id);
CREATE INDEX IF NOT EXISTS pos_cash_move_line_idx ON pos_cash_move (statement_line_id);

CREATE TABLE IF NOT EXISTS pos_cake (
    cake_id INTEGER PRIMARY KEY,
    reference TEXT,
    status TEXT,
    config_id INTEGER,
    config_name TEXT,
    session_id INTEGER,
    session_name TEXT,
    cashier TEXT,
    partner_name TEXT,
    partner_phone TEXT,
    product_name TEXT,
    size_name TEXT,
    pieces INTEGER,
    sugar_paste INTEGER,
    components TEXT,
    note TEXT,
    cake_base_cost REAL,
    components_cost REAL,
    price_before_tax REAL,
    tax_amount REAL,
    final_price REAL,
    production_name TEXT,
    created_at TEXT,
    pay_later INTEGER DEFAULT 0,
    loaded_at TEXT,
    pos_order_uuid TEXT,
    first_seen TEXT,
    last_update TEXT
);
"""

ADVANCE_STATE_BY_ACTION = {
    "advance_created": "deposited",
    "advance_completed": "completed",
    "advance_refunded": "refunded",
}
# Names sent by version 1.1 of the POS module.
LEGACY_EVENT_ACTIONS = {
    "created": "advance_created",
    "completed": "advance_completed",
    "refunded": "advance_refunded",
    "failed": "advance_failed",
}
FAILED_EVENT_ACTIONS = ("advance_failed", "pledge_return_failed", "cake_failed", "cash_move_failed",
                        "cash_delivery_failed")
CASH_MOVE_TYPES = {
    "cash_in": "Cash in",
    "cash_out": "Cash out",
    "cash_delivery": "Cash delivery",
    "closing_delivery": "Closing delivery",
}
# Tables whose rows carry session_id / session_name.
SESSION_TABLES = ("pos_order", "pos_advance", "pos_pledge_return", "pos_cash_move", "pos_cake")
CAKE_STATE_LABELS = {"waiting_payment": "Waiting for payment", "in_order": "In a POS order", "paid": "Paid"}

# A cake counts as paid once the POS order that carries it is paid.
CAKE_SOURCE = (
    "(SELECT c.*, o.state AS order_state, o.pos_reference AS order_ref, "
    "CASE WHEN o.state IN ('paid', 'done', 'invoiced') THEN 'paid' ELSE c.status END AS cake_state "
    "FROM pos_cake c LEFT JOIN pos_order o ON o.uuid = c.pos_order_uuid)"
)

# Group value shown (and used in links) for records where the grouped field is empty.
EMPTY_GROUP = "(empty)"

# Per list screen: table, search conditions, sort, "Group by" choices (label, SQL) and totals per group.
# A grouping without SQL is handled by BackupDB.group_records itself.
LIST_SPECS = {
    "orders": {
        "source": "pos_order",
        "clauses": "_order_clauses",
        "order_by": "date_order DESC, last_update DESC",
        "groups": {
            "day": ("Day", "substr(date_order, 1, 10)"),
            "session": ("Session", "session_name"),
            "register": ("Register", "config_name"),
            "cashier": ("Cashier", "cashier"),
            "state": ("Status", "state"),
            "customer": ("Customer", "partner_name"),
            "fiscal": ("Fiscal position", "fiscal_position"),
            "payment": ("Payment method", None),
            "origin": ("Origin", "COALESCE(source, 'pos')"),
            "synced": ("Sent to server", "CASE WHEN synced_to_server = 1 THEN 'Yes' ELSE 'No' END"),
        },
        "sums": [("Total", "SUM(amount_total)"), ("Paid", "SUM(amount_paid)")],
    },
    "advances": {
        "source": "pos_advance",
        "clauses": "_advance_clauses",
        "order_by": "COALESCE(created_at, first_seen) DESC",
        "groups": {
            "day": ("Day", "substr(COALESCE(created_at, first_seen), 1, 10)"),
            "state": ("Status", "state"),
            "customer": ("Customer", "partner_name"),
            "method": ("Deposit method", "payment_method_name"),
            "register": ("Register", "config_name"),
            "cashier": ("Cashier", "cashier"),
        },
        "sums": [("Total", "SUM(amount_total)"), ("Deposits", "SUM(advance_amount)")],
    },
    "pledge_returns": {
        "source": "pos_pledge_return",
        "clauses": "_pledge_return_clauses",
        "order_by": "ts DESC, id DESC",
        "groups": {
            "day": ("Day", "substr(ts, 1, 10)"),
            "customer": ("Customer", "partner_name"),
            "method": ("Paid back via", "payment_method_name"),
            "register": ("Register", "config_name"),
            "cashier": ("Cashier", "cashier"),
        },
        "sums": [("Amount", "SUM(total_amount)"), ("Pledges", "SUM(pledge_count)")],
    },
    "cakes": {
        "source": CAKE_SOURCE,
        "clauses": "_cake_clauses",
        "order_by": "COALESCE(created_at, first_seen) DESC",
        "groups": {
            "day": ("Day", "substr(COALESCE(created_at, first_seen), 1, 10)"),
            "state": ("Status", "cake_state"),
            "customer": ("Customer", "partner_name"),
            "size": ("Size", "size_name"),
            "register": ("Register", "config_name"),
            "cashier": ("Cashier", "cashier"),
        },
        "sums": [("Final price", "SUM(final_price)")],
    },
    "cash_moves": {
        "source": "pos_cash_move",
        "clauses": "_cash_move_clauses",
        "order_by": "ts DESC, id DESC",
        "groups": {
            "day": ("Day", "substr(ts, 1, 10)"),
            "session": ("Session", "session_name"),
            "type": ("Type", "move_type"),
            "cashier": ("Cashier", "cashier"),
            "source": ("Made from", "source"),
            "register": ("Register", "config_name"),
        },
        "sums": [
            ("In", "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END)"),
            ("Out", "SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END)"),
            ("Net", "SUM(amount)"),
        ],
    },
    "logs": {
        "source": "event_log",
        "clauses": "_log_clauses",
        "order_by": "id DESC",
        "groups": {
            "day": ("Day", "substr(ts, 1, 10)"),
            "event": ("Event", "event"),
            "level": ("Level", "level"),
        },
        "sums": [],
    },
}

ORDER_COLUMNS = [
    "pos_reference", "name", "config_id", "config_name", "session_id", "session_name",
    "date_order", "partner_id", "partner_name", "cashier", "state", "fiscal_position", "amount_total",
    "amount_tax", "amount_paid", "amount_return",
]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sql_quote(value):
    return "'" + value.replace("'", "''") + "'"


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _money(value):
    number = _number(value)
    return "" if number is None else f"{number:.3f}"


def advance_key(advance_id):
    """Value stored in event_log.order_uuid so advance events link to the advance page."""
    return f"advance:{advance_id}" if advance_id is not None else None


def pledge_return_key(return_id):
    return f"pledge-return:{return_id}"


def cake_key(cake_id):
    return f"cake:{cake_id}" if cake_id is not None else None


def cash_move_key(row_id):
    return f"cash-move:{row_id}"


class BackupDB:
    def __init__(self, path, password, allow_unencrypted=False):
        self.path = path
        self.lock = threading.RLock()
        self.session_names = {}
        self.encrypted = sqlcipher is not None
        if self.encrypted:
            self.conn = sqlcipher.connect(path, check_same_thread=False)
            self.conn.execute(f"PRAGMA key = {_sql_quote(password)}")
            try:
                self.conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            except sqlcipher.DatabaseError as error:
                raise RuntimeError("Wrong database password or corrupted database file.") from error
            self.conn.row_factory = sqlcipher.Row
        elif allow_unencrypted:
            _logger.warning("sqlcipher3 is not installed: the database is NOT encrypted (development mode).")
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        else:
            raise RuntimeError("sqlcipher3 is not installed; cannot open an encrypted database.")
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self._migrate_event_table()
            self.conn.executescript(SCHEMA)
            # Databases created by older versions miss these columns.
            order_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(pos_order)")}
            for column, kind in (("source", "TEXT"), ("fiscal_position", "TEXT"), ("cake_order_id", "INTEGER")):
                if column not in order_columns:
                    self.conn.execute(f"ALTER TABLE pos_order ADD COLUMN {column} {kind}")
            self.conn.commit()

    def _migrate_event_table(self):
        """Version 1.1 kept only advance events, in pos_advance_event with short action names."""
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "pos_advance_event" in tables and "pos_event" not in tables:
            self.conn.execute("ALTER TABLE pos_advance_event RENAME TO pos_event")
            self.conn.execute(
                "UPDATE pos_event SET action = 'advance_' || action "
                "WHERE action IN ('created', 'completed', 'refunded', 'failed')"
            )
            self.conn.commit()

    def rekey(self, new_password):
        if not self.encrypted:
            raise RuntimeError("The database is not encrypted (sqlcipher3 missing).")
        with self.lock:
            self.conn.execute(f"PRAGMA rekey = {_sql_quote(new_password)}")
            self.conn.commit()

    # -- events ------------------------------------------------------------

    def log(self, level, event, message="", order_uuid=None, order_ref=None, commit=True):
        with self.lock:
            self.conn.execute(
                "INSERT INTO event_log (ts, level, event, order_uuid, order_ref, message) VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), level, event, order_uuid, order_ref, message),
            )
            if commit:
                self.conn.commit()
        log_method = _logger.warning if level in ("warning", "error") else _logger.info
        log_method("[%s] %s %s", event, order_ref or order_uuid or "", message)

    # -- session names ---------------------------------------------------------

    def _session_name(self, session_id, name):
        """
        Odoo calls a session "/" until its opening cash is confirmed, and an open POS
        page keeps that name. Returns the real name when known, and gives it to the
        records already stored as "/" once it arrives.
        """
        session_id = _integer(session_id)
        if session_id is None:
            return name
        if not name or name == "/":
            known = self.session_names.get(session_id)
            if known is None:
                row = self.conn.execute(
                    "SELECT session_name FROM pos_order WHERE session_id = ? "
                    "AND session_name IS NOT NULL AND session_name NOT IN ('', '/') LIMIT 1",
                    (session_id,),
                ).fetchone()
                known = row[0] if row else ""
                if known:
                    self.session_names[session_id] = known
            return known or name
        if self.session_names.get(session_id) != name:
            self.session_names[session_id] = name
            fixed = 0
            for table in SESSION_TABLES:
                fixed += self.conn.execute(
                    f"UPDATE {table} SET session_name = ? WHERE session_id = ? "
                    "AND (session_name IS NULL OR session_name IN ('', '/'))",
                    (name, session_id),
                ).rowcount
            if fixed:
                self.log("info", "session_named", f"{fixed} record(s) saved as '/' now show session {name}",
                         commit=False)
        return name

    # -- orders --------------------------------------------------------------

    def upsert_orders(self, orders):
        result = {"created": 0, "updated": 0, "errors": 0}
        with self.lock:
            for order in orders:
                try:
                    created = self._upsert_order(order)
                    result["created" if created else "updated"] += 1
                except (ValueError, TypeError, *DB_ERRORS) as error:
                    result["errors"] += 1
                    self.log(
                        "error", "order_rejected", str(error),
                        order_uuid=str(order.get("uuid", ""))[:64] if isinstance(order, dict) else None,
                        commit=False,
                    )
            self.conn.commit()
        return result

    def _upsert_order(self, order):
        if not isinstance(order, dict):
            raise ValueError("order must be an object")
        uuid = order.get("uuid")
        if not isinstance(uuid, str) or not uuid or len(uuid) > 64:
            raise ValueError("invalid order uuid")
        ref = order.get("pos_reference") or order.get("name") or uuid
        server_id = order.get("server_id") or None
        values = {col: order.get(col) for col in ORDER_COLUMNS}
        values["session_name"] = self._session_name(values["session_id"], values["session_name"])
        values["synced_to_server"] = 1 if server_id else 0
        values["server_id"] = server_id
        values["payload_json"] = json.dumps(order.get("payload"), ensure_ascii=False, default=str)
        values["last_update"] = _now()
        values["fiscal_position"] = values["fiscal_position"] or ""
        if order.get("source"):
            values["source"] = str(order["source"])[:32]
        cake_order_id = _integer(order.get("cake_order_id"))
        if cake_order_id is not None:
            values["cake_order_id"] = cake_order_id

        existing = self.conn.execute(
            "SELECT state, amount_total, server_id, deleted, fiscal_position FROM pos_order WHERE uuid = ?", (uuid,)
        ).fetchone()

        if existing is None:
            values["uuid"] = uuid
            values["first_seen"] = values["last_update"]
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            self.conn.execute(
                f"INSERT INTO pos_order ({columns}) VALUES ({placeholders})", list(values.values())
            )
            self.log(
                "info", "order_created",
                f"state={values['state']} total={values['amount_total']}"
                + (f" fiscal position={values['fiscal_position']}" if values["fiscal_position"] else ""),
                order_uuid=uuid, order_ref=ref, commit=False,
            )
        else:
            assignments = ", ".join(f"{col} = ?" for col in values)
            self.conn.execute(
                f"UPDATE pos_order SET {assignments}, deleted = 0 WHERE uuid = ?",
                [*values.values(), uuid],
            )
            if existing["state"] != values["state"]:
                self.log(
                    "info", "state_changed",
                    f"{existing['state']} -> {values['state']} (total={values['amount_total']})",
                    order_uuid=uuid, order_ref=ref, commit=False,
                )
            elif values["state"] != "draft" and existing["amount_total"] != values["amount_total"]:
                self.log(
                    "warning", "amount_changed",
                    f"{existing['amount_total']} -> {values['amount_total']} on a {values['state']} order",
                    order_uuid=uuid, order_ref=ref, commit=False,
                )
            if (existing["fiscal_position"] or "") != values["fiscal_position"]:
                self.log(
                    "info", "fiscal_position_changed",
                    f"{existing['fiscal_position'] or 'none'} -> {values['fiscal_position'] or 'none'}",
                    order_uuid=uuid, order_ref=ref, commit=False,
                )
            if server_id and not existing["server_id"]:
                self.log(
                    "info", "synced_to_server", f"server id {server_id}",
                    order_uuid=uuid, order_ref=ref, commit=False,
                )
            if existing["deleted"]:
                self.log("warning", "order_reappeared", "order was marked deleted before",
                         order_uuid=uuid, order_ref=ref, commit=False)

        self.conn.execute("DELETE FROM pos_order_line WHERE order_uuid = ?", (uuid,))
        for line in order.get("lines") or []:
            self.conn.execute(
                "INSERT OR REPLACE INTO pos_order_line (uuid, order_uuid, product_id, product_name, qty, "
                "price_unit, discount, price_subtotal, price_subtotal_incl) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(line.get("uuid") or secrets.token_hex(8)), uuid, line.get("product_id"),
                    line.get("product_name"), line.get("qty"), line.get("price_unit"), line.get("discount"),
                    line.get("price_subtotal"), line.get("price_subtotal_incl"),
                ),
            )
        self.conn.execute("DELETE FROM pos_payment WHERE order_uuid = ?", (uuid,))
        for payment in order.get("payments") or []:
            self.conn.execute(
                "INSERT OR REPLACE INTO pos_payment (uuid, order_uuid, payment_method_id, "
                "payment_method_name, amount, payment_date) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(payment.get("uuid") or secrets.token_hex(8)), uuid, payment.get("payment_method_id"),
                    payment.get("payment_method_name"), payment.get("amount"), payment.get("payment_date"),
                ),
            )
        if cake_order_id is not None:
            self.conn.execute(
                "UPDATE pos_cake SET pos_order_uuid = ?, last_update = ? WHERE cake_id = ?",
                (uuid, values["last_update"], cake_order_id),
            )
        return existing is None

    def mark_deleted(self, items):
        count = 0
        with self.lock:
            for item in items:
                uuid = item.get("uuid") if isinstance(item, dict) else None
                if not isinstance(uuid, str) or not uuid:
                    continue
                row = self.conn.execute(
                    "SELECT pos_reference, state, amount_total FROM pos_order WHERE uuid = ?", (uuid,)
                ).fetchone()
                if row is None:
                    continue
                self.conn.execute(
                    "UPDATE pos_order SET deleted = 1, deleted_at = ? WHERE uuid = ?", (_now(), uuid)
                )
                self.log(
                    "warning", "order_deleted",
                    f"state={row['state']} total={row['amount_total']}",
                    order_uuid=uuid, order_ref=row["pos_reference"], commit=False,
                )
                count += 1
            self.conn.commit()
        return count

    # -- events (actions done on the server: advances, pledges, cakes, cash) ----

    def record_events(self, events):
        result = {"accepted": 0, "duplicates": 0, "errors": 0}
        with self.lock:
            for event in events:
                # A half-recorded event would be skipped as a duplicate when the POS sends it again.
                self.conn.execute("SAVEPOINT pos_event")
                try:
                    accepted = self._record_event(event)
                    self.conn.execute("RELEASE pos_event")
                    result["accepted" if accepted else "duplicates"] += 1
                except (ValueError, TypeError, AttributeError, *DB_ERRORS) as error:
                    self.conn.execute("ROLLBACK TO pos_event")
                    self.conn.execute("RELEASE pos_event")
                    # A session rename done inside the rolled back event must be redone later.
                    self.session_names.clear()
                    result["errors"] += 1
                    action = event.get("action") if isinstance(event, dict) else None
                    self.log("error", "event_rejected", f"{action or 'event'}: {error}", commit=False)
            self.conn.commit()
        return result

    def _event_handlers(self):
        return {
            "advance_created": self._record_advance,
            "advance_completed": self._record_advance,
            "advance_refunded": self._record_advance,
            "advance_failed": self._record_advance,
            "pledge_returned": self._record_pledge_return,
            "pledge_return_failed": self._record_pledge_return,
            "cake_created": self._record_cake,
            "cake_pay_later": self._record_cake,
            "cake_loaded": self._record_cake,
            "cake_failed": self._record_cake,
            "cash_move": self._record_cash_move,
            "cash_move_failed": self._record_cash_move,
            "cash_move_deleted": self._record_cash_move_deleted,
            "cash_moves_snapshot": self._record_cash_moves_snapshot,
            "cash_delivery": self._record_delivery,
            "closing_delivery": self._record_delivery,
            "cash_delivery_failed": self._record_delivery,
        }

    def _record_event(self, event):
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        event_uuid = event.get("event_uuid")
        if not isinstance(event_uuid, str) or not event_uuid or len(event_uuid) > 64:
            raise ValueError("invalid event id")
        action = LEGACY_EVENT_ACTIONS.get(event.get("action"), event.get("action"))
        handler = self._event_handlers().get(action)
        if handler is None:
            raise ValueError(f"unknown event action {action!r}")
        event["action"] = action
        event["session_name"] = self._session_name(event.get("session_id"), event.get("session_name"))
        # The POS retries until it gets an answer, so the same event may arrive twice.
        if self.conn.execute("SELECT 1 FROM pos_event WHERE event_uuid = ?", (event_uuid,)).fetchone():
            return False
        advance = event.get("advance") if isinstance(event.get("advance"), dict) else {}
        self.conn.execute(
            "INSERT INTO pos_event (event_uuid, advance_id, reference, action, ts, received_at, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_uuid, _integer(advance.get("id")), self._event_reference(event), action,
             event.get("ts") or _now(), _now(), json.dumps(event, ensure_ascii=False, default=str)),
        )
        handler(event_uuid, action, event)
        return True

    @staticmethod
    def _event_reference(event):
        for key in ("advance", "cake"):
            if isinstance(event.get(key), dict) and event[key].get("reference"):
                return event[key]["reference"]
        refund_names = ", ".join(
            o.get("refund_order_name") for o in event.get("refund_orders") or []
            if isinstance(o, dict) and o.get("refund_order_name")
        )
        return refund_names or event.get("partner_name") or event.get("reason") or ""

    def _upsert_row(self, table, key_column, key, values):
        # Keep what earlier events stored when a later event does not carry the value.
        values = {k: v for k, v in values.items() if v not in (None, "")}
        values["last_update"] = _now()
        exists = self.conn.execute(f"SELECT 1 FROM {table} WHERE {key_column} = ?", (key,)).fetchone()
        if exists:
            assignments = ", ".join(f"{col} = ?" for col in values)
            self.conn.execute(f"UPDATE {table} SET {assignments} WHERE {key_column} = ?", [*values.values(), key])
        else:
            values[key_column] = key
            values["first_seen"] = values["last_update"]
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            self.conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(values.values()))

    @staticmethod
    def _event_origin(event):
        return {
            "config_id": _integer(event.get("config_id")),
            "config_name": event.get("config_name"),
            "session_id": _integer(event.get("session_id")),
            "session_name": event.get("session_name"),
            "cashier": event.get("cashier"),
        }

    # -- advance orders --------------------------------------------------------

    def _record_advance(self, event_uuid, action, event):
        advance = event.get("advance") if isinstance(event.get("advance"), dict) else {}
        advance_id = _integer(advance.get("id"))
        reference = advance.get("reference") or ""
        ts = event.get("ts") or _now()

        if action == "advance_failed":
            customer = advance.get("partner_name")
            self.log(
                "error", "advance_failed",
                f"{event.get('failed_action') or 'advance'} failed: {event.get('error') or '-'}"
                + (f" (customer {customer})" if customer else ""),
                order_uuid=advance_key(advance_id), order_ref=reference or None, commit=False,
            )
            return
        if advance_id is None:
            raise ValueError(f"{action} event without advance id")

        values = {
            "reference": reference,
            "config_id": _integer(event.get("config_id")),
            "config_name": event.get("config_name"),
            "partner_name": advance.get("partner_name"),
            "partner_phone": advance.get("partner_phone"),
            "amount_total": _number(advance.get("amount_total")),
            "advance_amount": _number(advance.get("advance_amount")),
            "pledge_amount": _number(advance.get("pledge_amount")),
            "state": ADVANCE_STATE_BY_ACTION[action],
        }
        key = advance_key(advance_id)

        if action == "advance_created":
            values.update({
                "session_id": _integer(event.get("session_id")),
                "session_name": event.get("session_name"),
                "cashier": event.get("cashier"),
                "amount_tendered": _number(advance.get("amount_tendered")),
                "change_amount": _number(advance.get("change_amount")),
                "amount_remaining": _number(advance.get("amount_remaining")),
                "payment_method_name": advance.get("payment_method_name"),
                "created_at": ts,
            })
            self._upsert_row("pos_advance", "advance_id", advance_id, values)
            self.conn.execute("DELETE FROM pos_advance_line WHERE advance_id = ?", (advance_id,))
            for line in event.get("lines") or []:
                self.conn.execute(
                    "INSERT INTO pos_advance_line (advance_id, product_id, product_name, qty, price_unit, discount, subtotal) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (advance_id, _integer(line.get("product_id")), line.get("product_name"), _number(line.get("qty")),
                     _number(line.get("price_unit")), _number(line.get("discount")), _number(line.get("subtotal"))),
                )
            self.log(
                "info", "advance_created",
                f"deposit {_money(values['advance_amount'])} of {_money(values['amount_total'])} "
                f"via {values['payment_method_name'] or '-'}, customer {values['partner_name'] or '-'}",
                order_uuid=key, order_ref=reference, commit=False,
            )
        elif action == "advance_completed":
            completion = event.get("completion") if isinstance(event.get("completion"), dict) else {}
            order_uuid = self._save_advance_completion_order(advance_id, event, advance, completion, ts)
            values.update({
                "completed_at": ts,
                "completion_order_ref": completion.get("pos_order_name"),
                "completion_order_uuid": order_uuid,
                "remaining_paid": _number(completion.get("remaining_paid")),
                "completion_payment_method": completion.get("payment_method_name"),
            })
            self._upsert_row("pos_advance", "advance_id", advance_id, values)
            self.log(
                "info", "advance_completed",
                f"remaining {_money(values['remaining_paid'])} paid via {values['completion_payment_method'] or '-'}, "
                f"POS order {values['completion_order_ref'] or '-'}",
                order_uuid=key, order_ref=reference, commit=False,
            )
        else:
            refund = event.get("refund") if isinstance(event.get("refund"), dict) else {}
            values.update({
                "refunded_at": ts,
                "refund_amount": _number(refund.get("amount")),
                "refund_payment_method": refund.get("payment_method_name"),
            })
            self._upsert_row("pos_advance", "advance_id", advance_id, values)
            self.log(
                "warning", "advance_refunded",
                f"deposit {_money(values['refund_amount'])} refunded via {values['refund_payment_method'] or '-'}",
                order_uuid=key, order_ref=reference, commit=False,
            )

    def _record_pledge_return(self, event_uuid, action, event):
        ts = event.get("ts") or _now()
        pledges = [p for p in (event.get("pledges") or []) if isinstance(p, dict)]
        refund_orders = [o for o in (event.get("refund_orders") or []) if isinstance(o, dict)]
        refund_names = ", ".join(o.get("refund_order_name") or "" for o in refund_orders if o.get("refund_order_name"))
        customer = event.get("partner_name") or "-"
        if action == "pledge_return_failed":
            self.log(
                "error", "pledge_return_failed",
                f"{len(pledges)} pledge(s) of customer {customer}, {_money(event.get('total_amount'))} "
                f"via {event.get('payment_method_name') or '-'}: {event.get('error') or '-'}",
                commit=False,
            )
            return

        cursor = self.conn.execute(
            "INSERT INTO pos_pledge_return (event_uuid, ts, config_id, config_name, session_id, session_name, cashier, "
            "partner_name, partner_phone, payment_method_name, total_amount, pledge_count, refund_orders, "
            "origin_orders, return_move_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_uuid, ts, _integer(event.get("config_id")), event.get("config_name"),
                _integer(event.get("session_id")), event.get("session_name"), event.get("cashier"),
                event.get("partner_name"), event.get("partner_phone"), event.get("payment_method_name"),
                _number(event.get("total_amount")), len(pledges), refund_names,
                ", ".join(o.get("origin_order_name") or "" for o in refund_orders if o.get("origin_order_name")),
                event.get("return_move_name") or "",
            ),
        )
        return_id = cursor.lastrowid

        refund_by_pledge = {}
        for refund in refund_orders:
            for pledge_id in refund.get("pledge_ids") or []:
                refund_by_pledge[_integer(pledge_id)] = refund.get("refund_order_name")
        for pledge in pledges:
            pledge_id = _integer(pledge.get("id"))
            self.conn.execute(
                "INSERT INTO pos_pledge_return_line (return_id, pledge_id, reference, product_name, qty, amount, "
                "employee_name, refund_order_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (return_id, pledge_id, pledge.get("reference"), pledge.get("product_name"), _number(pledge.get("qty")),
                 _number(pledge.get("amount")), pledge.get("employee_name"), refund_by_pledge.get(pledge_id)),
            )

        for refund in refund_orders:
            self._save_pledge_refund_order(event, refund, pledges, ts)

        self.log(
            "warning", "pledge_returned",
            f"{len(pledges)} pledge(s) of customer {customer}, {_money(event.get('total_amount'))} returned "
            f"via {event.get('payment_method_name') or '-'}"
            + (f", refund order {refund_names}" if refund_names else "")
            + (f", entry {event.get('return_move_name')}" if event.get("return_move_name") else ""),
            order_uuid=pledge_return_key(return_id), order_ref=refund_names or customer, commit=False,
        )

    def _save_pledge_refund_order(self, event, refund, pledges, ts):
        """Store the refund POS order the server created to give the pledge money back."""
        refund_id = _integer(refund.get("refund_order_id"))
        name = refund.get("refund_order_name") or ""
        if refund_id is None and not name:
            return
        order_uuid = f"pledge-return-{refund_id if refund_id is not None else name}"[:64]
        wanted = {_integer(pid) for pid in refund.get("pledge_ids") or []}
        group = [p for p in pledges if _integer(p.get("id")) in wanted] or pledges
        amount = _number(refund.get("amount")) or 0.0
        self._upsert_order({
            "uuid": order_uuid,
            "pos_reference": name,
            "name": name,
            "config_id": _integer(event.get("config_id")),
            "config_name": event.get("config_name"),
            "session_id": _integer(event.get("session_id")),
            "session_name": event.get("session_name"),
            "date_order": ts,
            "partner_name": event.get("partner_name"),
            "cashier": event.get("cashier"),
            "state": "paid",
            "amount_total": -amount,
            "amount_paid": -amount,
            "amount_return": 0,
            "server_id": refund_id,
            "source": "pledge_return",
            "payload": {"origin_order_name": refund.get("origin_order_name"), "refund": refund},
            "lines": [
                {
                    "uuid": f"{order_uuid}-line-{index}"[:64],
                    "product_name": f"{p.get('product_name') or ''} (pledge return {p.get('reference') or ''})",
                    "qty": -(_number(p.get("qty")) or 0),
                    "price_unit": _number(p.get("unit_amount")),
                    "price_subtotal_incl": -(_number(p.get("amount")) or 0),
                }
                for index, p in enumerate(group)
            ],
            "payments": [
                {"uuid": f"{order_uuid}-payment"[:64], "payment_method_name": refund.get("payment_method_name")
                 or event.get("payment_method_name"), "amount": -amount, "payment_date": ts},
            ],
        })
        self.conn.execute("UPDATE pos_order SET synced_to_server = 1 WHERE uuid = ?", (order_uuid,))

    def _save_advance_completion_order(self, advance_id, event, advance, completion, ts):
        """Store the POS order the server created when the advance was completed."""
        order_uuid = f"advance-{advance_id}-order"
        order_ref = completion.get("pos_order_name") or f"{advance.get('reference') or advance_id} (completion)"
        advance_amount = _number(advance.get("advance_amount")) or 0.0
        remaining_paid = _number(completion.get("remaining_paid")) or 0.0
        lines = [
            {
                "uuid": f"{order_uuid}-line-{index}",
                "product_id": line.get("product_id"),
                "product_name": line.get("product_name"),
                "qty": line.get("qty"),
                "discount": line.get("discount"),
                "price_subtotal_incl": line.get("subtotal"),
            }
            for index, line in enumerate(completion.get("lines") or [])
        ]
        payments = [
            {"uuid": f"{order_uuid}-deposit", "payment_method_name": completion.get("advance_payment_method_name")
             or "Advance deposit", "amount": advance_amount, "payment_date": ts},
            {"uuid": f"{order_uuid}-remaining", "payment_method_name": completion.get("payment_method_name"),
             "amount": remaining_paid, "payment_date": ts},
        ]
        self._upsert_order({
            "uuid": order_uuid,
            "pos_reference": order_ref,
            "name": order_ref,
            "config_id": _integer(event.get("config_id")),
            "config_name": event.get("config_name"),
            "session_id": _integer(event.get("session_id")),
            "session_name": event.get("session_name"),
            "date_order": ts,
            "partner_name": advance.get("partner_name"),
            "cashier": event.get("cashier"),
            "state": "paid",
            "amount_total": _number(advance.get("amount_total")),
            "amount_paid": advance_amount + remaining_paid,
            "amount_return": _number(completion.get("change_amount")),
            "source": "advance",
            "payload": {"advance_reference": advance.get("reference"), "completion": completion},
            "lines": lines,
            "payments": payments,
        })
        # The server created this order itself, so it is already there.
        self.conn.execute("UPDATE pos_order SET synced_to_server = 1 WHERE uuid = ?", (order_uuid,))
        return order_uuid

    # -- custom cakes ------------------------------------------------------------

    def _record_cake(self, event_uuid, action, event):
        ts = event.get("ts") or _now()
        if action == "cake_failed":
            self.log(
                "error", "cake_failed",
                f"{event.get('failed_action') or 'cake'} failed: {event.get('error') or '-'}",
                commit=False,
            )
            return
        cake = event.get("cake") if isinstance(event.get("cake"), dict) else {}
        form = event.get("form") if isinstance(event.get("form"), dict) else {}
        cake_id = _integer(cake.get("id"))
        if cake_id is None:
            raise ValueError(f"{action} event without cake id")
        components = ", ".join(
            f"{c.get('category')}: {c.get('product_name')}" if c.get("category") else str(c.get("product_name") or "")
            for c in form.get("components") or [] if isinstance(c, dict)
        )
        values = {
            "reference": cake.get("reference"),
            "partner_name": cake.get("partner_name"),
            "partner_phone": form.get("phone"),
            "product_name": cake.get("product_name"),
            "size_name": form.get("size_name"),
            "pieces": _integer(cake.get("pieces")),
            "sugar_paste": 1 if cake.get("sugar_paste") else 0,
            "components": components,
            "note": cake.get("note"),
            "cake_base_cost": _number(cake.get("cake_base_cost")),
            "components_cost": _number(cake.get("total_components_cost")),
            "price_before_tax": _number(cake.get("price_before_tax")),
            "tax_amount": _number(cake.get("tax_amount")),
            "final_price": _number(cake.get("final_price")),
            "production_name": cake.get("production_name"),
        }
        if action == "cake_loaded":
            # Loading happens later, maybe on another register: keep where the cake was ordered.
            values.update({"status": "in_order", "loaded_at": ts, "pos_order_uuid": event.get("pos_order_uuid")})
            message = f"loaded for payment, {_money(values['final_price'])}, customer {values['partner_name'] or '-'}"
            level = "info"
        else:
            values.update(self._event_origin(event))
            values["created_at"] = ts
            if action == "cake_pay_later":
                values.update({"status": "waiting_payment", "pay_later": 1})
                level, message = "warning", "saved to pay later"
            else:
                values.update({"status": "in_order", "pos_order_uuid": event.get("pos_order_uuid")})
                level, message = "info", "created and added to the POS order"
            message += (
                f", {_money(values['final_price'])}, customer {values['partner_name'] or '-'}"
                + (f", size {values['size_name']}" if values["size_name"] else "")
                + (f", MO {values['production_name']}" if values["production_name"] else "")
            )
        self._upsert_row("pos_cake", "cake_id", cake_id, values)
        self.log(level, action, message, order_uuid=cake_key(cake_id), order_ref=values["reference"], commit=False)

    # -- cash moves --------------------------------------------------------------

    def _insert_cash_move(self, move_key, values):
        values = {**values, "move_key": move_key, "first_seen": _now(), "last_update": _now()}
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        cursor = self.conn.execute(
            f"INSERT INTO pos_cash_move ({columns}) VALUES ({placeholders})", list(values.values())
        )
        return cursor.lastrowid

    def _record_cash_move(self, event_uuid, action, event):
        amount = abs(_number(event.get("amount")) or 0.0)
        move_type = "cash_in" if event.get("move_type") == "in" else "cash_out"
        reason = event.get("reason") or ""
        if action == "cash_move_failed":
            self.log(
                "error", "cash_move_failed",
                f"{CASH_MOVE_TYPES[move_type]} of {_money(amount)} ('{reason}') refused: {event.get('error') or '-'}",
                commit=False,
            )
            return
        queued = bool(event.get("queued_offline"))
        row_id = self._insert_cash_move(f"pos:{event_uuid}", {
            **self._event_origin(event),
            "ts": event.get("ts") or _now(),
            "move_type": move_type,
            "amount": amount if move_type == "cash_in" else -amount,
            "reason": reason,
            "source": "pos",
            "queued_offline": 1 if queued else 0,
            "details_json": json.dumps(event, ensure_ascii=False, default=str),
        })
        self.log(
            "info", move_type,
            f"{_money(amount)} '{reason}' by {event.get('cashier') or '-'}"
            + (" - no connection, the POS will send it to Odoo later" if queued else ""),
            order_uuid=cash_move_key(row_id), order_ref=CASH_MOVE_TYPES[move_type], commit=False,
        )

    def _record_cash_move_deleted(self, event_uuid, action, event):
        line_id = _integer(event.get("statement_line_id"))
        row = self.conn.execute(
            "SELECT * FROM pos_cash_move WHERE statement_line_id = ?", (line_id,)
        ).fetchone() if line_id is not None else None
        if row is not None and row["deleted"]:
            return
        if row is not None:
            self.conn.execute(
                "UPDATE pos_cash_move SET deleted = 1, deleted_at = ?, last_update = ? WHERE id = ?",
                (event.get("ts") or _now(), _now(), row["id"]),
            )
        self.log(
            "warning", "cash_move_deleted",
            f"{_money(abs(row['amount'] or 0)) if row is not None else ''} '{row['reason'] if row is not None else ''}'"
            f" deleted from the POS by {event.get('cashier') or '-'} (Odoo line {line_id})",
            order_uuid=cash_move_key(row["id"]) if row is not None else None,
            order_ref="Cash move", commit=False,
        )

    def _record_cash_moves_snapshot(self, event_uuid, action, event):
        """Reconcile with the session's cash in/out list read from Odoo."""
        session_id = _integer(event.get("session_id"))
        if session_id is None:
            raise ValueError("cash moves snapshot without session")
        seen = set()
        for move in event.get("moves") or []:
            if not isinstance(move, dict):
                continue
            line_id = _integer(move.get("id"))
            if line_id is None:
                continue
            seen.add(line_id)
            amount = _number(move.get("amount")) or 0.0
            name = move.get("name") or ""
            row = self.conn.execute(
                "SELECT * FROM pos_cash_move WHERE statement_line_id = ?", (line_id,)
            ).fetchone()
            if row is None:
                row = self._match_pos_cash_move(session_id, amount, name)
            if row is not None:
                self.conn.execute(
                    "UPDATE pos_cash_move SET statement_line_id = ?, name = ?, amount = ?, last_update = ? WHERE id = ?",
                    (line_id, name, amount, _now(), row["id"]),
                )
                if row["queued_offline"] and row["statement_line_id"] is None:
                    self.log(
                        "info", "cash_move_reached_odoo", f"{_money(abs(amount))} '{row['reason']}' is now in Odoo",
                        order_uuid=cash_move_key(row["id"]), order_ref=name, commit=False,
                    )
                continue
            move_type = "cash_in" if amount > 0 else "cash_out"
            row_id = self._insert_cash_move(f"absl:{line_id}", {
                **self._event_origin(event),
                "cashier": move.get("cashier_name") or "",
                "statement_line_id": line_id,
                "ts": move.get("date") or event.get("ts") or _now(),
                "move_type": move_type,
                "amount": amount,
                "reason": name,
                "name": name,
                "source": "odoo",
                "details_json": json.dumps(move, ensure_ascii=False, default=str),
            })
            self.log(
                "warning", "cash_move_from_odoo",
                f"{CASH_MOVE_TYPES[move_type]} {_money(abs(amount))} '{name}' added outside this POS"
                + (f" by {move.get('cashier_name')}" if move.get("cashier_name") else ""),
                order_uuid=cash_move_key(row_id), order_ref=name, commit=False,
            )

        gone = self.conn.execute(
            "SELECT * FROM pos_cash_move WHERE session_id = ? AND statement_line_id IS NOT NULL AND deleted = 0",
            (session_id,),
        ).fetchall()
        for row in gone:
            if row["statement_line_id"] in seen:
                continue
            self.conn.execute(
                "UPDATE pos_cash_move SET deleted = 1, deleted_at = ?, last_update = ? WHERE id = ?",
                (event.get("ts") or _now(), _now(), row["id"]),
            )
            self.log(
                "warning", "cash_move_deleted",
                f"{_money(abs(row['amount'] or 0))} '{row['reason']}' no longer exists in Odoo",
                order_uuid=cash_move_key(row["id"]), order_ref=row["name"] or "Cash move", commit=False,
            )

    def _match_pos_cash_move(self, session_id, amount, name):
        """Find the move typed on this POS that became this Odoo line (its name ends with the reason)."""
        candidates = self.conn.execute(
            "SELECT * FROM pos_cash_move WHERE session_id = ? AND source = 'pos' AND statement_line_id IS NULL "
            "AND deleted = 0 AND move_type IN ('cash_in', 'cash_out') AND ABS(amount - ?) < 0.0005 ORDER BY id",
            (session_id, amount),
        ).fetchall()
        for row in candidates:
            if name.endswith(row["reason"] or ""):
                return row
        return None

    def _record_delivery(self, event_uuid, action, event):
        amount = abs(_number(event.get("amount")) or 0.0)
        kind = event.get("delivery_type") if event.get("delivery_type") in CASH_MOVE_TYPES else "cash_delivery"
        available = _number(event.get("available_cash"))
        before = _number(event.get("delivered_before"))
        context = (
            (f", available cash {_money(available)}" if available is not None else "")
            + (f", already delivered {_money(before)}" if before else "")
        )
        if action == "cash_delivery_failed":
            self.log(
                "error", "cash_delivery_failed",
                f"{CASH_MOVE_TYPES[kind]} of {_money(amount)} refused: {event.get('error') or '-'}{context}",
                commit=False,
            )
            return
        reason = event.get("reason") or ""
        row_id = self._insert_cash_move(f"delivery:{event_uuid}", {
            **self._event_origin(event),
            "ts": event.get("ts") or _now(),
            "move_type": kind,
            "amount": -amount,
            "reason": reason,
            "source": "pos",
            "available_cash": available,
            "details_json": json.dumps(event, ensure_ascii=False, default=str),
        })
        self.log(
            "info", kind,
            (f"{_money(amount)} delivered" if amount else "zero amount confirmed by the cashier")
            + (f" '{reason}'" if reason else "") + context,
            order_uuid=cash_move_key(row_id), order_ref=CASH_MOVE_TYPES[kind], commit=False,
        )

    # -- queries ---------------------------------------------------------------

    def stats(self):
        with self.lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN state != 'draft' AND synced_to_server = 0 AND deleted = 0 THEN 1 ELSE 0 END) AS unsynced, "
                "SUM(CASE WHEN state = 'draft' AND deleted = 0 THEN 1 ELSE 0 END) AS open_orders, "
                "SUM(deleted) AS deleted, MAX(last_update) AS last_update FROM pos_order"
            ).fetchone()
            errors = self.conn.execute(
                "SELECT COUNT(*) FROM event_log WHERE level = 'error' AND ts >= date('now', '-1 day')"
            ).fetchone()[0]
            advances_open = self.conn.execute(
                "SELECT COUNT(*) FROM pos_advance WHERE state = 'deposited'"
            ).fetchone()[0]
            cakes_waiting = self.conn.execute(
                f"SELECT COUNT(*) FROM {CAKE_SOURCE} WHERE cake_state = 'waiting_payment'"
            ).fetchone()[0]
            cash_out_today = self.conn.execute(
                "SELECT COALESCE(SUM(-amount), 0) FROM pos_cash_move "
                "WHERE amount < 0 AND deleted = 0 AND ts >= date('now', 'localtime')"
            ).fetchone()[0]
        return {
            "total": row["total"] or 0,
            "unsynced": row["unsynced"] or 0,
            "open_orders": row["open_orders"] or 0,
            "deleted": row["deleted"] or 0,
            "last_update": row["last_update"] or "-",
            "errors_24h": errors,
            "advances_open": advances_open,
            "cakes_waiting": cakes_waiting,
            "cash_out_today": cash_out_today,
        }

    # Each builder returns the SQL conditions of one screen's search form.

    @staticmethod
    def _date_range(clauses, params, filters, expr):
        if filters.get("date_from"):
            clauses.append(f"{expr} >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            clauses.append(f"{expr} <= ?")
            params.append(filters["date_to"] + " 23:59:59")

    def _order_clauses(self, filters, clauses, params):
        if filters.get("q"):
            clauses.append("(pos_reference LIKE ? OR name LIKE ? OR partner_name LIKE ?)")
            params += [f"%{filters['q']}%"] * 3
        if filters.get("state"):
            clauses.append("state = ?")
            params.append(filters["state"])
        if filters.get("session"):
            clauses.append("(session_name LIKE ? OR CAST(session_id AS TEXT) = ?)")
            params += [f"%{filters['session']}%", filters["session"]]
        if filters.get("fiscal"):
            clauses.append("fiscal_position LIKE ?")
            params.append(f"%{filters['fiscal']}%")
        if filters.get("synced") == "no":
            clauses.append("synced_to_server = 0")
        elif filters.get("synced") == "yes":
            clauses.append("synced_to_server = 1")
        if filters.get("deleted") == "yes":
            clauses.append("deleted = 1")
        elif filters.get("deleted") != "all":
            clauses.append("deleted = 0")
        self._date_range(clauses, params, filters, "date_order")

    def _advance_clauses(self, filters, clauses, params):
        if filters.get("q"):
            clauses.append("(reference LIKE ? OR partner_name LIKE ? OR partner_phone LIKE ? OR completion_order_ref LIKE ?)")
            params += [f"%{filters['q']}%"] * 4
        if filters.get("state"):
            clauses.append("state = ?")
            params.append(filters["state"])
        self._date_range(clauses, params, filters, "COALESCE(created_at, first_seen)")

    def _pledge_return_clauses(self, filters, clauses, params):
        if filters.get("q"):
            clauses.append(
                "(partner_name LIKE ? OR partner_phone LIKE ? OR refund_orders LIKE ? OR origin_orders LIKE ? "
                "OR id IN (SELECT return_id FROM pos_pledge_return_line WHERE reference LIKE ? OR product_name LIKE ?))"
            )
            params += [f"%{filters['q']}%"] * 6
        self._date_range(clauses, params, filters, "ts")

    def _cake_clauses(self, filters, clauses, params):
        if filters.get("q"):
            clauses.append(
                "(reference LIKE ? OR partner_name LIKE ? OR partner_phone LIKE ? OR product_name LIKE ? "
                "OR production_name LIKE ? OR order_ref LIKE ?)"
            )
            params += [f"%{filters['q']}%"] * 6
        if filters.get("state"):
            clauses.append("cake_state = ?")
            params.append(filters["state"])
        self._date_range(clauses, params, filters, "COALESCE(created_at, first_seen)")

    def _cash_move_clauses(self, filters, clauses, params):
        if filters.get("q"):
            clauses.append("(reason LIKE ? OR name LIKE ? OR cashier LIKE ?)")
            params += [f"%{filters['q']}%"] * 3
        if filters.get("type"):
            clauses.append("move_type = ?")
            params.append(filters["type"])
        if filters.get("session"):
            clauses.append("(session_name LIKE ? OR CAST(session_id AS TEXT) = ?)")
            params += [f"%{filters['session']}%", filters["session"]]
        if filters.get("deleted") == "yes":
            clauses.append("deleted = 1")
        elif filters.get("deleted") != "all":
            clauses.append("deleted = 0")
        self._date_range(clauses, params, filters, "ts")

    def _log_clauses(self, filters, clauses, params):
        if filters.get("level"):
            clauses.append("level = ?")
            params.append(filters["level"])
        if filters.get("q"):
            clauses.append("(order_ref LIKE ? OR message LIKE ? OR event LIKE ?)")
            params += [f"%{filters['q']}%"] * 3
        self._date_range(clauses, params, filters, "ts")

    def _where(self, screen, filters):
        clauses, params = [], []
        getattr(self, LIST_SPECS[screen]["clauses"])(filters, clauses, params)
        # Values picked by clicking a line of a grouped list.
        for key, (_label, expr) in LIST_SPECS[screen]["groups"].items():
            value = filters.get(f"g_{key}")
            if not value:
                continue
            if expr is None:
                clauses.append(
                    "uuid IN (SELECT order_uuid FROM pos_payment WHERE COALESCE(payment_method_name, '') = ?)"
                )
            else:
                clauses.append(f"COALESCE({expr}, '') = ?")
            params.append("" if value == EMPTY_GROUP else value)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def list_records(self, screen, filters, page=1):
        spec = LIST_SPECS[screen]
        where, params = self._where(screen, filters)
        with self.lock:
            total = self.conn.execute(f"SELECT COUNT(*) FROM {spec['source']}{where}", params).fetchone()[0]
            rows = self.conn.execute(
                f"SELECT * FROM {spec['source']}{where} ORDER BY {spec['order_by']} LIMIT ? OFFSET ?",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            ).fetchall()
        return total, rows

    def group_records(self, screen, group_key, filters):
        """Return the sum labels and one row (grp, cnt, s0, s1...) per value of the chosen grouping."""
        spec = LIST_SPECS[screen]
        _label, expr = spec["groups"][group_key]
        where, params = self._where(screen, filters)
        if expr is None:
            sum_labels = ["Amount paid"]
            sql = (
                "SELECT COALESCE(payment_method_name, '') AS grp, COUNT(DISTINCT order_uuid) AS cnt, "
                f"SUM(amount) AS s0 FROM pos_payment WHERE order_uuid IN (SELECT uuid FROM pos_order{where}) "
                "GROUP BY grp ORDER BY cnt DESC"
            )
        else:
            sum_labels = [label for label, _sql in spec["sums"]]
            sums = "".join(f", {sql} AS s{index}" for index, (_l, sql) in enumerate(spec["sums"]))
            order = "grp DESC" if group_key == "day" else "cnt DESC, grp"
            sql = (
                f"SELECT COALESCE({expr}, '') AS grp, COUNT(*) AS cnt{sums} FROM {spec['source']}{where} "
                f"GROUP BY grp ORDER BY {order} LIMIT 500"
            )
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return sum_labels, rows

    def _events_of(self, key):
        return self.conn.execute("SELECT * FROM event_log WHERE order_uuid = ? ORDER BY id DESC", (key,)).fetchall()

    def get_order(self, uuid):
        with self.lock:
            order = self.conn.execute("SELECT * FROM pos_order WHERE uuid = ?", (uuid,)).fetchone()
            lines = self.conn.execute("SELECT * FROM pos_order_line WHERE order_uuid = ?", (uuid,)).fetchall()
            payments = self.conn.execute("SELECT * FROM pos_payment WHERE order_uuid = ?", (uuid,)).fetchall()
            events = self._events_of(uuid)
        return order, lines, payments, events

    def export_orders(self, scope, session=None):
        if scope == "unsynced":
            where, params = " WHERE synced_to_server = 0 AND state != 'draft'", []
        elif scope == "session":
            where, params = " WHERE session_name LIKE ? OR CAST(session_id AS TEXT) = ?", [f"%{session}%", session or ""]
        else:
            where, params = "", []
        with self.lock:
            orders = self.conn.execute(f"SELECT * FROM pos_order{where} ORDER BY date_order", params).fetchall()
            result = []
            for order in orders:
                lines = self.conn.execute(
                    "SELECT * FROM pos_order_line WHERE order_uuid = ?", (order["uuid"],)
                ).fetchall()
                payments = self.conn.execute(
                    "SELECT * FROM pos_payment WHERE order_uuid = ?", (order["uuid"],)
                ).fetchall()
                data = dict(order)
                data["payload"] = json.loads(data.pop("payload_json") or "null")
                data["lines"] = [dict(line) for line in lines]
                data["payments"] = [dict(payment) for payment in payments]
                result.append(data)
        return result

    def get_advance(self, advance_id):
        with self.lock:
            advance = self.conn.execute("SELECT * FROM pos_advance WHERE advance_id = ?", (advance_id,)).fetchone()
            lines = self.conn.execute(
                "SELECT * FROM pos_advance_line WHERE advance_id = ? ORDER BY id", (advance_id,)
            ).fetchall()
            events = self._events_of(advance_key(advance_id))
            history = self.conn.execute(
                "SELECT * FROM pos_event WHERE advance_id = ? ORDER BY ts, received_at", (advance_id,)
            ).fetchall()
        return advance, lines, events, history

    def failed_events(self, actions):
        placeholders = ", ".join("?" for _ in actions)
        with self.lock:
            rows = self.conn.execute(
                f"SELECT payload_json FROM pos_event WHERE action IN ({placeholders}) ORDER BY ts", list(actions)
            ).fetchall()
        return [json.loads(row["payload_json"] or "null") for row in rows]

    def export_advances(self):
        with self.lock:
            advances = self.conn.execute(
                "SELECT * FROM pos_advance ORDER BY COALESCE(created_at, first_seen)"
            ).fetchall()
            result = []
            for advance in advances:
                data = dict(advance)
                data["lines"] = [
                    dict(line) for line in self.conn.execute(
                        "SELECT * FROM pos_advance_line WHERE advance_id = ? ORDER BY id", (advance["advance_id"],)
                    ).fetchall()
                ]
                data["events"] = [
                    json.loads(row["payload_json"] or "null") for row in self.conn.execute(
                        "SELECT payload_json FROM pos_event WHERE advance_id = ? ORDER BY ts, received_at",
                        (advance["advance_id"],),
                    ).fetchall()
                ]
                result.append(data)
            pledge_returns = []
            for row in self.conn.execute("SELECT * FROM pos_pledge_return ORDER BY ts").fetchall():
                data = dict(row)
                data["lines"] = [
                    dict(line) for line in self.conn.execute(
                        "SELECT * FROM pos_pledge_return_line WHERE return_id = ? ORDER BY id", (row["id"],)
                    ).fetchall()
                ]
                pledge_returns.append(data)
        failed = self.failed_events(("advance_failed", "pledge_return_failed"))
        return result, failed, pledge_returns

    def get_pledge_return(self, return_id):
        with self.lock:
            row = self.conn.execute("SELECT * FROM pos_pledge_return WHERE id = ?", (return_id,)).fetchone()
            if row is None:
                return None, [], [], None
            lines = self.conn.execute(
                "SELECT * FROM pos_pledge_return_line WHERE return_id = ? ORDER BY id", (return_id,)
            ).fetchall()
            events = self._events_of(pledge_return_key(return_id))
            payload = self.conn.execute(
                "SELECT payload_json FROM pos_event WHERE event_uuid = ?", (row["event_uuid"],)
            ).fetchone()
        return row, lines, events, payload["payload_json"] if payload else None

    def pledge_refund_order_uuids(self, names):
        if not names:
            return {}
        placeholders = ", ".join("?" for _ in names)
        with self.lock:
            rows = self.conn.execute(
                f"SELECT uuid, pos_reference FROM pos_order WHERE source = 'pledge_return' "
                f"AND pos_reference IN ({placeholders})",
                list(names),
            ).fetchall()
        return {row["pos_reference"]: row["uuid"] for row in rows}

    def get_cake(self, cake_id):
        with self.lock:
            cake = self.conn.execute(f"SELECT * FROM {CAKE_SOURCE} WHERE cake_id = ?", (cake_id,)).fetchone()
            if cake is None:
                return None, [], []
            events = self._events_of(cake_key(cake_id))
            history = self.conn.execute(
                "SELECT * FROM pos_event WHERE action LIKE 'cake%' AND reference = ? ORDER BY ts, received_at",
                (cake["reference"] or "",),
            ).fetchall()
        return cake, events, history

    def export_cakes(self):
        with self.lock:
            rows = self.conn.execute(f"SELECT * FROM {CAKE_SOURCE} ORDER BY COALESCE(created_at, first_seen)").fetchall()
        return [dict(row) for row in rows], self.failed_events(("cake_failed",))

    def get_cash_move(self, row_id):
        with self.lock:
            row = self.conn.execute("SELECT * FROM pos_cash_move WHERE id = ?", (row_id,)).fetchone()
            events = self._events_of(cash_move_key(row_id)) if row is not None else []
        return row, events

    def export_cash_moves(self):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM pos_cash_move ORDER BY ts, id").fetchall()
        moves = []
        for row in rows:
            data = dict(row)
            data["details"] = json.loads(data.pop("details_json") or "null")
            moves.append(data)
        return moves, self.failed_events(("cash_move_failed", "cash_delivery_failed"))


# ---------------------------------------------------------------------------
# Web screens
# ---------------------------------------------------------------------------

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f5f7;color:#222}
header{background:#714b67;color:#fff;padding:12px 20px;display:flex;justify-content:space-between;align-items:center}
header a{color:#fff;margin-left:16px;text-decoration:none;font-weight:600}
header a.active{text-decoration:underline}
main{padding:20px}
table{border-collapse:collapse;width:100%;background:#fff}
th,td{border-bottom:1px solid #e3e3e3;padding:6px 8px;text-align:left;font-size:14px}
th{background:#fafafa}
.card{background:#fff;padding:16px;border-radius:6px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.metric{font-size:28px;font-weight:700}
.badge{padding:2px 8px;border-radius:10px;font-size:12px;color:#fff}
.b-info{background:#2f80ed}.b-warning{background:#f2994a}.b-error{background:#eb5757}
.b-yes{background:#27ae60}.b-no{background:#eb5757}.b-draft{background:#999}
form.filters input,form.filters select{padding:5px;margin-right:6px}
button,input[type=submit]{background:#714b67;color:#fff;border:0;padding:6px 14px;border-radius:4px;cursor:pointer}
.pager a{margin-right:10px}
.login{max-width:320px;margin:80px auto}
.login input{width:100%;padding:8px;margin:8px 0;box-sizing:border-box}
.err{color:#eb5757}
pre{white-space:pre-wrap;word-break:break-all;background:#fafafa;padding:10px;max-height:400px;overflow:auto}
.chip{display:inline-block;background:#efe6ed;border-radius:12px;padding:2px 10px;margin-right:6px}
.chip a{text-decoration:none;font-weight:700;color:#714b67}
"""

TABS = [
    ("status", "Status"), ("orders", "Orders"), ("advances", "Advances"), ("cakes", "Special cakes"),
    ("cash-moves", "Cash moves"), ("logs", "Logs"), ("export", "Export"),
]

ADVANCE_STATE_LABELS = {"deposited": "Deposit paid", "completed": "Completed", "refunded": "Refunded"}

# Readable names for stored codes, used in lists and in "Group by" results.
GROUP_VALUE_LABELS = {
    ("advances", "state"): ADVANCE_STATE_LABELS,
    ("cakes", "state"): CAKE_STATE_LABELS,
    ("cash_moves", "type"): CASH_MOVE_TYPES,
    ("cash_moves", "source"): {"pos": "This POS", "odoo": "Odoo backend"},
    ("orders", "origin"): {"pos": "POS", "advance": "Advance completion", "pledge_return": "Pledge return",
                           "cake": "Custom cake"},
}


def esc(value):
    return html.escape("" if value is None else str(value))


def page(title, body, active=None):
    nav = "".join(
        f'<a href="/{key}" class="{"active" if key == active else ""}">{label}</a>' for key, label in TABS
    )
    nav_html = f"<nav>{nav}<a href='/logout'>Logout</a></nav>" if active else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{esc(title)} - {APP_TITLE}</title><style>{CSS}</style></head><body>"
        f"<header><strong>{APP_TITLE}</strong>{nav_html}</header><main>{body}</main></body></html>"
    )


def pager(base_path, filters, page_number, total):
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    links = []
    if page_number > 1:
        links.append(f'<a href="{base_path}?{urlencode({**filters, "page": page_number - 1})}">&laquo; Previous</a>')
    links.append(f"Page {page_number} / {pages} ({total} records)")
    if page_number < pages:
        links.append(f'<a href="{base_path}?{urlencode({**filters, "page": page_number + 1})}">Next &raquo;</a>')
    return f"<div class='pager'>{' '.join(links)}</div>"


def yes_no(flag):
    return '<span class="badge b-yes">Yes</span>' if flag else '<span class="badge b-no">No</span>'


def state_badges(row):
    badges = f"<span class='badge b-draft'>{esc(row['state'])}</span>"
    if row["deleted"]:
        badges += " <span class='badge b-error'>deleted</span>"
    if row["source"] == "advance":
        badges += " <span class='badge b-info'>from advance</span>"
    elif row["source"] == "pledge_return":
        badges += " <span class='badge b-warning'>pledge return</span>"
    elif row["source"] == "cake":
        badges += " <span class='badge b-info'>custom cake</span>"
    return badges


def advances_subnav(active):
    links = [("/advances", "Advance orders"), ("/pledge-returns", "Pledge returns")]
    return "<div class='card'>" + " | ".join(
        f"<strong>{label}</strong>" if path == active else f"<a href='{path}'>{label}</a>" for path, label in links
    ) + "</div>"


def advance_state_badge(state):
    css = {"deposited": "b-warning", "completed": "b-yes", "refunded": "b-error"}.get(state, "b-draft")
    return f"<span class='badge {css}'>{esc(ADVANCE_STATE_LABELS.get(state, state))}</span>"


def cake_state_badge(state):
    css = {"waiting_payment": "b-warning", "in_order": "b-info", "paid": "b-yes"}.get(state, "b-draft")
    return f"<span class='badge {css}'>{esc(CAKE_STATE_LABELS.get(state, state))}</span>"


def cash_move_status(row):
    if row["deleted"]:
        return "<span class='badge b-error'>deleted</span>"
    if row["move_type"] in ("cash_delivery", "closing_delivery"):
        return "<span class='badge b-yes'>delivered</span>"
    if row["statement_line_id"]:
        return "<span class='badge b-yes'>in Odoo</span>"
    if row["queued_offline"]:
        return "<span class='badge b-warning'>waiting for connection</span>"
    return "<span class='badge b-draft'>sent</span>"


def order_link(uuid, label):
    if not uuid:
        return esc(label or "")
    prefixes = {
        "advance:": "/advance", "pledge-return:": "/pledge-return", "cake:": "/cake", "cash-move:": "/cash-move",
    }
    for prefix, path in prefixes.items():
        if uuid.startswith(prefix):
            return f"<a href='{path}?{urlencode({'id': uuid[len(prefix):]})}'>{esc(label or uuid)}</a>"
    return f"<a href='/order?{urlencode({'uuid': uuid})}'>{esc(label or uuid)}</a>"


def format_total(value):
    # Counts (SUM of integers) stay integers; amounts get 3 decimals.
    return esc(value) if isinstance(value, int) else _money(value or 0)


def events_table(events):
    rows = "".join(
        f"<tr><td>{esc(e['ts'])}</td><td><span class='badge b-{esc(e['level'])}'>{esc(e['level'])}</span></td>"
        f"<td>{esc(e['event'])}</td><td>{esc(e['message'])}</td></tr>"
        for e in events
    )
    return (
        "<div class='card'><h3>Events</h3><table><tr><th>Time</th><th>Level</th><th>Event</th><th>Message</th></tr>"
        f"{rows}</table></div>"
    )


def pretty_json(text):
    try:
        return json.dumps(json.loads(text or "null"), indent=2, ensure_ascii=False)
    except ValueError:
        return text


def group_value_label(screen, key, value):
    if value == "":
        return EMPTY_GROUP
    return GROUP_VALUE_LABELS.get((screen, key), {}).get(value, value)


def group_controls(screen, filters):
    """'Group by' choice plus the values already picked from a grouped list, kept when searching again."""
    groups = LIST_SPECS[screen]["groups"]
    options = "".join(
        f"<option value='{key}'{' selected' if filters.get('group') == key else ''}>{esc(label)}</option>"
        for key, (label, _expr) in groups.items()
    )
    hidden = "".join(
        f"<input type='hidden' name='g_{key}' value='{esc(filters[f'g_{key}'])}'>"
        for key in groups if filters.get(f"g_{key}")
    )
    return f"<select name='group'><option value=''>No grouping</option>{options}</select>{hidden}"


def group_chips(base_path, screen, filters):
    chips = []
    for key, (label, _expr) in LIST_SPECS[screen]["groups"].items():
        value = filters.get(f"g_{key}")
        if not value:
            continue
        rest = {k: v for k, v in filters.items() if k != f"g_{key}"}
        shown = group_value_label(screen, key, "" if value == EMPTY_GROUP else value)
        chips.append(
            f"<span class='chip'>{esc(label)}: {esc(shown)} <a href='{base_path}?{urlencode(rest)}' "
            "title='Remove'>&times;</a></span>"
        )
    return f"<div class='card'>Showing only: {' '.join(chips)}</div>" if chips else ""


def grouped_table(base_path, screen, filters, sum_labels, rows):
    key = filters["group"]
    label = LIST_SPECS[screen]["groups"][key][0]
    head = f"<tr><th>{esc(label)}</th><th>Count</th>" + "".join(f"<th>{esc(s)}</th>" for s in sum_labels) + "</tr>"
    body = []
    totals = [0] * len(sum_labels)
    count = 0
    for row in rows:
        value = row["grp"]
        drill = {**{k: v for k, v in filters.items() if k != "group"}, f"g_{key}": value if value != "" else EMPTY_GROUP}
        cells = ""
        for index in range(len(sum_labels)):
            amount = row[f"s{index}"] or 0
            totals[index] += amount
            cells += f"<td>{format_total(amount)}</td>"
        count += row["cnt"]
        body.append(
            f"<tr><td><a href='{base_path}?{urlencode(drill)}'>{esc(group_value_label(screen, key, value))}</a></td>"
            f"<td>{esc(row['cnt'])}</td>{cells}</tr>"
        )
    total_cells = "".join(f"<th>{format_total(total)}</th>" for total in totals)
    footer = f"<tr><th>Total</th><th>{count}</th>{total_cells}</tr>" if rows else ""
    return f"<p>Click a line to see its records.</p><table>{head}{''.join(body)}{footer}</table>"


def list_filters(screen, params, keys):
    filters = {key: params.get(key, "") for key in keys}
    if params.get("group") in LIST_SPECS[screen]["groups"]:
        filters["group"] = params["group"]
    for key in LIST_SPECS[screen]["groups"]:
        if params.get(f"g_{key}"):
            filters[f"g_{key}"] = params[f"g_{key}"]
    return filters


def select_field(name, filters, choices):
    return f"<select name='{name}'>" + "".join(
        f"<option value='{esc(value)}'{' selected' if filters.get(name) == value else ''}>{esc(label)}</option>"
        for value, label in choices
    ) + "</select>"


def date_fields(filters):
    return (
        f"<input type='date' name='date_from' value='{esc(filters.get('date_from'))}' title='From'>"
        f"<input type='date' name='date_to' value='{esc(filters.get('date_to'))}' title='To'>"
    )


class HelperServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, config, db):
        super().__init__(address, RequestHandler)
        self.config = config
        self.db = db
        self.api_key = config["api_key"]
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        self.login_failures = 0
        self.login_locked_until = 0.0
        self.last_rejection_log = {}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = f"AnabtawiPOSBackup/{VERSION}"

    def log_message(self, fmt, *args):  # noqa: D401 - silence default stderr logging
        return

    # -- helpers -------------------------------------------------------------

    @property
    def db(self):
        return self.server.db

    def _query(self):
        parsed = urlparse(self.path)
        return parsed.path, {k: v[-1] for k, v in parse_qs(parsed.query).items()}

    def _origin_allowed(self, origin):
        if not origin:
            return False
        return any(fnmatch.fnmatch(origin, pattern) for pattern in self.server.config["allowed_origins"])

    def _cors_headers(self):
        origin = self.headers.get("Origin")
        if self._origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")

    def _send(self, status, body, content_type="text/html; charset=utf-8", headers=None, cors=False):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if not cors:
            self.send_header("X-Frame-Options", "DENY")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if cors:
            self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json", cors=True)

    def _redirect(self, location, headers=None):
        self.send_response(303)
        self.send_header("Location", location)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ValueError("request too large")
        return self.rfile.read(length) if length else b""

    # -- auth ----------------------------------------------------------------

    def _api_authorized(self):
        origin = self.headers.get("Origin")
        if not self._origin_allowed(origin):
            self._log_rejection("origin_not_allowed", f"request from website {origin or '(none)'} is not in the allowed list")
            return False
        key = self.headers.get("X-Api-Key") or ""
        if not hmac.compare_digest(key.encode(), self.server.api_key.encode()):
            self._log_rejection("wrong_api_key", f"request from {origin} used a wrong API key")
            return False
        return True

    def _log_rejection(self, event, message):
        # At most one entry per reason per minute, the POS retries every few seconds.
        now = time.time()
        last = self.server.last_rejection_log.get(event, 0)
        if now - last >= 60:
            self.server.last_rejection_log[event] = now
            self.db.log("error", event, message)

    def _session_token(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = cookies.SimpleCookie()
        jar.load(raw)
        morsel = jar.get("pbsid")
        return morsel.value if morsel else None

    def _ui_authorized(self):
        token = self._session_token()
        if not token:
            return False
        with self.server.sessions_lock:
            expiry = self.server.sessions.get(token)
            if not expiry or expiry < time.time():
                self.server.sessions.pop(token, None)
                return False
        return True

    # -- routing -------------------------------------------------------------

    def do_OPTIONS(self):
        origin = self.headers.get("Origin")
        allowed = self._origin_allowed(origin)
        if not allowed:
            self._log_rejection("origin_not_allowed", f"request from website {origin or '(none)'} is not in the allowed list")
        self.send_response(204 if allowed else 403)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path, params = self._query()
        try:
            if path == "/api/health":
                if not self._api_authorized():
                    return self._json(401, {"error": "unauthorized"})
                return self._json(200, {"status": "ok", "version": VERSION, "encrypted": self.db.encrypted,
                                        **self.db.stats()})
            if path == "/login":
                return self._send(200, self._login_page())
            if path == "/logout":
                return self._logout()
            if not self._ui_authorized():
                return self._redirect("/login")
            routes = {
                "/": lambda: self._redirect("/status"),
                "/status": lambda: self._status_page(),
                "/orders": lambda: self._orders_page(params),
                "/order": lambda: self._order_page(params),
                "/advances": lambda: self._advances_page(params),
                "/advance": lambda: self._advance_page(params),
                "/pledge-returns": lambda: self._pledge_returns_page(params),
                "/pledge-return": lambda: self._pledge_return_page(params),
                "/cakes": lambda: self._cakes_page(params),
                "/cake": lambda: self._cake_page(params),
                "/cash-moves": lambda: self._cash_moves_page(params),
                "/cash-move": lambda: self._cash_move_page(params),
                "/logs": lambda: self._logs_page(params),
                "/export": lambda: self._export_page(),
                "/export/download": lambda: self._export_download(params),
            }
            handler = routes.get(path)
            if handler is None:
                return self._send(404, page("Not found", "<p>Page not found.</p>", "status"))
            return handler()
        except Exception as error:  # keep the service alive whatever happens
            _logger.exception("GET %s failed", path)
            return self._send(500, page("Error", f"<p class='err'>{esc(error)}</p>"))

    def do_POST(self):
        path, _ = self._query()
        try:
            if path == "/login":
                return self._login(self._read_body())
            if not path.startswith("/api/"):
                return self._send(404, "Not found", "text/plain")
            if not self._api_authorized():
                return self._json(401, {"error": "unauthorized"})
            payload = json.loads(self._read_body() or b"{}")
            if path == "/api/orders":
                return self._json(200, self.db.upsert_orders(payload.get("orders") or []))
            if path == "/api/orders/deleted":
                return self._json(200, {"deleted": self.db.mark_deleted(payload.get("orders") or [])})
            # /api/advances is the address used by version 1.1 of the POS module.
            if path in ("/api/events", "/api/advances"):
                return self._json(200, self.db.record_events(payload.get("events") or []))
            return self._json(404, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as error:
            self.db.log("error", "bad_request", f"{path}: {error}")
            return self._json(400, {"error": str(error)})
        except Exception as error:
            _logger.exception("POST %s failed", path)
            self.db.log("error", "server_error", f"{path}: {error}")
            return self._json(500, {"error": str(error)})

    # -- login ---------------------------------------------------------------

    def _login_page(self, error=""):
        error_html = f"<p class='err'>{esc(error)}</p>" if error else ""
        body = (
            "<div class='card login'><h3>Manager login</h3>"
            f"{error_html}<form method='post' action='/login'>"
            "<input type='password' name='pin' placeholder='Manager PIN' autofocus required>"
            "<input type='submit' value='Login'></form></div>"
        )
        return page("Login", body)

    def _login(self, body):
        server = self.server
        if server.login_locked_until > time.time():
            wait = int(server.login_locked_until - time.time())
            return self._send(429, self._login_page(f"Too many attempts. Try again in {wait} seconds."))
        pin = parse_qs(body.decode("utf-8")).get("pin", [""])[-1]
        if not verify_pin(pin, server.config["admin_pin_hash"]):
            server.login_failures += 1
            if server.login_failures >= MAX_LOGIN_FAILURES:
                server.login_locked_until = time.time() + LOGIN_LOCK_SECONDS
                server.login_failures = 0
            self.db.log("warning", "login_failed", "wrong manager PIN on the logs screen")
            return self._send(401, self._login_page("Wrong PIN."))
        server.login_failures = 0
        token = secrets.token_urlsafe(32)
        with server.sessions_lock:
            server.sessions[token] = time.time() + server.config["session_hours"] * 3600
        self.db.log("info", "login", "manager opened the logs screen")
        return self._redirect(
            "/status", {"Set-Cookie": f"pbsid={token}; HttpOnly; SameSite=Strict; Path=/"}
        )

    def _logout(self):
        token = self._session_token()
        if token:
            with self.server.sessions_lock:
                self.server.sessions.pop(token, None)
        return self._redirect("/login", {"Set-Cookie": "pbsid=; Max-Age=0; Path=/"})

    # -- pages ---------------------------------------------------------------

    def _status_page(self):
        stats = self.db.stats()
        encrypted = "Yes (SQLCipher)" if self.db.encrypted else "<span class='err'>NO - development mode</span>"
        size_mb = os.path.getsize(self.db.path) / (1024 * 1024) if os.path.exists(self.db.path) else 0
        metrics = [
            ("Orders stored", stats["total"]),
            ("Paid, not on server", stats["unsynced"]),
            ("Open orders", stats["open_orders"]),
            ("Deleted orders", stats["deleted"]),
            ("Advances awaiting completion", stats["advances_open"]),
            ("Cakes waiting for payment", stats["cakes_waiting"]),
            ("Cash out today (incl. deliveries)", _money(stats["cash_out_today"])),
            ("Errors (24h)", stats["errors_24h"]),
        ]
        cards = "".join(
            f"<div class='card'><div>{esc(label)}</div><div class='metric'>{esc(value)}</div></div>"
            for label, value in metrics
        )
        body = (
            f"<div class='grid'>{cards}</div>"
            "<div class='card'><table>"
            f"<tr><th>Service</th><td>Running - version {VERSION}</td></tr>"
            f"<tr><th>Database</th><td>{esc(self.db.path)} ({size_mb:.2f} MB)</td></tr>"
            f"<tr><th>Encrypted</th><td>{encrypted}</td></tr>"
            f"<tr><th>Last order received</th><td>{esc(stats['last_update'])}</td></tr>"
            f"<tr><th>Allowed Odoo sites</th><td>{esc(', '.join(self.server.config['allowed_origins']))}</td></tr>"
            f"<tr><th>Log files</th><td>{esc(log_dir())}</td></tr>"
            "</table></div>"
        )
        return self._send(200, page("Status", body, "status"))

    def _list_page(self, screen, path, params, keys, fields, columns, cells, title, tab, before=""):
        """Search form, then either the records (paged) or, with 'Group by', one line per group with totals."""
        page_number = max(1, int(params.get("page") or 1))
        filters = list_filters(screen, params, keys)
        form = (
            f"<form class='filters card' method='get' action='{path}'>{fields(filters)}"
            f"{group_controls(screen, filters)}<input type='submit' value='Search'></form>"
        )
        if filters.get("group"):
            sum_labels, rows = self.db.group_records(screen, filters["group"], filters)
            content = grouped_table(path, screen, filters, sum_labels, rows)
        else:
            total, rows = self.db.list_records(screen, filters, page_number)
            header = "".join(f"<th>{esc(column)}</th>" for column in columns)
            rows_html = "".join(f"<tr>{cells(row)}</tr>" for row in rows)
            content = pager(path, filters, page_number, total) + f"<table><tr>{header}</tr>{rows_html}</table>"
        body = before + form + group_chips(path, screen, filters) + f"<div class='card'>{content}</div>"
        return self._send(200, page(title, body, tab))

    def _orders_page(self, params):
        def fields(filters):
            return (
                f"<input name='q' placeholder='Reference / customer' value='{esc(filters['q'])}'>"
                f"<input name='session' placeholder='Session' value='{esc(filters['session'])}'>"
                f"<input name='fiscal' placeholder='Fiscal position' value='{esc(filters['fiscal'])}'>"
                + select_field("state", filters, [("", "Any status"), ("draft", "New (draft)"), ("paid", "Paid"),
                                                  ("done", "Posted"), ("cancel", "Cancelled")])
                + select_field("synced", filters, [("", "Sent to server?"), ("no", "Not sent"), ("yes", "Sent")])
                + select_field("deleted", filters, [("", "Hide deleted"), ("yes", "Deleted only"),
                                                    ("all", "Include deleted")])
                + date_fields(filters)
            )

        def cells(row):
            return (
                f"<td>{order_link(row['uuid'], row['pos_reference'] or row['name'])}</td>"
                f"<td>{esc(row['date_order'])}</td><td>{esc(row['config_name'])}</td><td>{esc(row['session_name'])}</td>"
                f"<td>{esc(row['partner_name'])}</td><td>{esc(row['cashier'])}</td><td>{esc(row['fiscal_position'])}</td>"
                f"<td>{state_badges(row)}</td>"
                f"<td>{row['amount_total'] or 0:.3f}</td><td>{row['amount_paid'] or 0:.3f}</td>"
                f"<td>{yes_no(row['synced_to_server'])}</td><td>{esc(row['last_update'])}</td>"
            )

        return self._list_page(
            "orders", "/orders", params,
            ("q", "state", "session", "fiscal", "synced", "deleted", "date_from", "date_to"), fields,
            ["Reference", "Date", "Register", "Session", "Customer", "Cashier", "Fiscal position", "Status",
             "Total", "Paid", "On server", "Last update"],
            cells, "Orders", "orders",
        )

    def _order_page(self, params):
        order, lines, payments, events = self.db.get_order(params.get("uuid", ""))
        if order is None:
            return self._send(404, page("Order", "<p>Order not found.</p>", "orders"))
        info_rows = "".join(
            f"<tr><th>{esc(label)}</th><td>{esc(order[key])}</td></tr>"
            for label, key in [
                ("Reference", "pos_reference"), ("Order name", "name"), ("UUID", "uuid"), ("Register", "config_name"),
                ("Session", "session_name"), ("Date", "date_order"), ("Customer", "partner_name"),
                ("Cashier", "cashier"), ("Status", "state"), ("Fiscal position", "fiscal_position"),
                ("Total", "amount_total"), ("Tax", "amount_tax"),
                ("Paid", "amount_paid"), ("Change", "amount_return"), ("Server ID", "server_id"),
                ("First seen", "first_seen"), ("Last update", "last_update"), ("Deleted at", "deleted_at"),
            ]
        )
        origin = GROUP_VALUE_LABELS[("orders", "origin")].get(order["source"] or "pos", order["source"])
        if order["cake_order_id"]:
            origin += " - " + order_link(cake_key(order["cake_order_id"]), "see the cake order")
        line_rows = "".join(
            f"<tr><td>{esc(line['product_name'])}</td><td>{esc(line['qty'])}</td><td>{esc(line['price_unit'])}</td>"
            f"<td>{esc(line['discount'])}</td><td>{esc(line['price_subtotal'])}</td><td>{esc(line['price_subtotal_incl'])}</td></tr>"
            for line in lines
        )
        payment_rows = "".join(
            f"<tr><td>{esc(p['payment_method_name'])}</td><td>{esc(p['amount'])}</td><td>{esc(p['payment_date'])}</td></tr>"
            for p in payments
        )
        body = (
            f"<div class='card'><table>{info_rows}<tr><th>Origin</th><td>{origin}</td></tr>"
            f"<tr><th>On server</th><td>{yes_no(order['synced_to_server'])}</td></tr></table></div>"
            "<div class='card'><h3>Lines</h3><table><tr><th>Product</th><th>Qty</th><th>Unit price</th><th>Discount %</th>"
            f"<th>Subtotal</th><th>Subtotal incl. tax</th></tr>{line_rows}</table></div>"
            f"<div class='card'><h3>Payments</h3><table><tr><th>Method</th><th>Amount</th><th>Date</th></tr>{payment_rows}</table></div>"
            + events_table(events)
            + f"<div class='card'><h3>Full data (as stored by the browser)</h3><pre>{esc(pretty_json(order['payload_json']))}</pre></div>"
        )
        return self._send(200, page("Order", body, "orders"))

    def _advances_page(self, params):
        def fields(filters):
            return (
                f"<input name='q' placeholder='Reference / customer / phone' value='{esc(filters['q'])}'>"
                + select_field("state", filters, [("", "Any status"), *ADVANCE_STATE_LABELS.items()])
                + date_fields(filters)
            )

        def cells(row):
            return (
                f"<td>{order_link(advance_key(row['advance_id']), row['reference'])}</td>"
                f"<td>{esc(row['created_at'] or row['first_seen'])}</td><td>{esc(row['config_name'])}</td>"
                f"<td>{esc(row['partner_name'])}</td><td>{esc(row['partner_phone'])}</td>"
                f"<td>{advance_state_badge(row['state'])}</td>"
                f"<td>{_money(row['amount_total'])}</td><td>{_money(row['advance_amount'])}</td>"
                f"<td>{esc(row['payment_method_name'])}</td>"
                f"<td>{order_link(row['completion_order_uuid'], row['completion_order_ref'])}</td>"
                f"<td>{esc(row['last_update'])}</td>"
            )

        return self._list_page(
            "advances", "/advances", params, ("q", "state", "date_from", "date_to"), fields,
            ["Reference", "Created", "Register", "Customer", "Phone", "Status", "Total", "Deposit", "Deposit method",
             "Completion order", "Last update"],
            cells, "Advances", "advances", before=advances_subnav("/advances"),
        )

    def _advance_page(self, params):
        advance_id = _integer(params.get("id"))
        advance, lines, events, history = self.db.get_advance(advance_id) if advance_id is not None else (None,) * 4
        if advance is None:
            return self._send(404, page("Advance", "<p>Advance order not found.</p>", "advances"))
        info = [
            ("Reference", esc(advance["reference"])), ("Odoo ID", esc(advance["advance_id"])),
            ("Status", advance_state_badge(advance["state"])), ("Register", esc(advance["config_name"])),
            ("Session", esc(advance["session_name"])), ("Cashier", esc(advance["cashier"])),
            ("Customer", esc(advance["partner_name"])), ("Phone", esc(advance["partner_phone"])),
            ("Total", _money(advance["amount_total"])), ("Pledge amount", _money(advance["pledge_amount"])),
            ("Created", esc(advance["created_at"])), ("Deposit", _money(advance["advance_amount"])),
            ("Deposit method", esc(advance["payment_method_name"])),
            ("Amount tendered", _money(advance["amount_tendered"])), ("Change", _money(advance["change_amount"])),
            ("Remaining after deposit", _money(advance["amount_remaining"])),
            ("Completed", esc(advance["completed_at"])), ("Remaining paid", _money(advance["remaining_paid"])),
            ("Completion method", esc(advance["completion_payment_method"])),
            ("Completion order", order_link(advance["completion_order_uuid"], advance["completion_order_ref"])),
            ("Refunded", esc(advance["refunded_at"])), ("Refund amount", _money(advance["refund_amount"])),
            ("Refund method", esc(advance["refund_payment_method"])),
            ("First seen", esc(advance["first_seen"])), ("Last update", esc(advance["last_update"])),
        ]
        info_rows = "".join(f"<tr><th>{esc(label)}</th><td>{value}</td></tr>" for label, value in info)
        line_rows = "".join(
            f"<tr><td>{esc(line['product_name'])}</td><td>{esc(line['qty'])}</td><td>{_money(line['price_unit'])}</td>"
            f"<td>{esc(line['discount'])}</td><td>{_money(line['subtotal'])}</td></tr>"
            for line in lines
        )
        lines_card = (
            "<div class='card'><h3>Lines (at creation)</h3><table><tr><th>Product</th><th>Qty</th><th>Unit price</th>"
            f"<th>Discount %</th><th>Subtotal</th></tr>{line_rows}</table></div>"
            if lines else
            "<div class='card'><h3>Lines</h3><p>The advance was created before this PC recorded advances, "
            "or on another register. See the completion order for its lines.</p></div>"
        )
        body = (
            f"<div class='card'><table>{info_rows}</table></div>{lines_card}"
            + events_table(events)
            + f"<div class='card'><h3>Full data (as sent by the POS)</h3>{self._history_blocks(history)}</div>"
        )
        return self._send(200, page("Advance", body, "advances"))

    @staticmethod
    def _history_blocks(history):
        return "".join(
            f"<h4>{esc(h['ts'])} - {esc(h['action'])}</h4><pre>{esc(pretty_json(h['payload_json']))}</pre>"
            for h in history
        )

    def _refund_order_links(self, names_text):
        names = [name.strip() for name in (names_text or "").split(",") if name.strip()]
        uuids = self.db.pledge_refund_order_uuids(names)
        return ", ".join(order_link(uuids.get(name), name) for name in names)

    def _pledge_returns_page(self, params):
        def fields(filters):
            return (
                f"<input name='q' placeholder='Customer / phone / pledge / order' value='{esc(filters['q'])}'>"
                + date_fields(filters)
            )

        def cells(row):
            return (
                f"<td>{order_link(pledge_return_key(row['id']), row['ts'])}</td><td>{esc(row['config_name'])}</td>"
                f"<td>{esc(row['cashier'])}</td><td>{esc(row['partner_name'])}</td><td>{esc(row['partner_phone'])}</td>"
                f"<td>{esc(row['pledge_count'])}</td><td>{_money(row['total_amount'])}</td>"
                f"<td>{esc(row['payment_method_name'])}</td>"
                f"<td>{self._refund_order_links(row['refund_orders']) or esc(row['return_move_name'])}</td>"
            )

        return self._list_page(
            "pledge_returns", "/pledge-returns", params, ("q", "date_from", "date_to"), fields,
            ["Returned at", "Register", "Cashier", "Customer", "Phone", "Pledges", "Amount", "Paid back via",
             "Refund order / entry"],
            cells, "Pledge returns", "advances", before=advances_subnav("/pledge-returns"),
        )

    def _pledge_return_page(self, params):
        return_id = _integer(params.get("id"))
        row, lines, events, payload_json = (
            self.db.get_pledge_return(return_id) if return_id is not None else (None, [], [], None)
        )
        if row is None:
            return self._send(404, page("Pledge return", "<p>Pledge return not found.</p>", "advances"))
        info = [
            ("Returned at", esc(row["ts"])), ("Register", esc(row["config_name"])),
            ("Session", esc(row["session_name"])), ("Cashier", esc(row["cashier"])),
            ("Customer", esc(row["partner_name"])), ("Phone", esc(row["partner_phone"])),
            ("Pledges returned", esc(row["pledge_count"])), ("Amount", _money(row["total_amount"])),
            ("Paid back via", esc(row["payment_method_name"])),
            ("Refund order(s)", self._refund_order_links(row["refund_orders"])),
            ("Original order(s)", esc(row["origin_orders"])), ("Reversal entry", esc(row["return_move_name"])),
        ]
        info_rows = "".join(f"<tr><th>{esc(label)}</th><td>{value}</td></tr>" for label, value in info)
        line_rows = "".join(
            f"<tr><td>{esc(line['reference'])}</td><td>{esc(line['product_name'])}</td><td>{esc(line['qty'])}</td>"
            f"<td>{_money(line['amount'])}</td><td>{esc(line['employee_name'])}</td>"
            f"<td>{esc(line['refund_order_name'])}</td></tr>"
            for line in lines
        )
        body = (
            advances_subnav("/pledge-returns")
            + f"<div class='card'><table>{info_rows}</table></div>"
            "<div class='card'><h3>Pledges</h3><table><tr><th>Pledge</th><th>Product</th><th>Qty</th><th>Amount</th>"
            f"<th>Employee</th><th>Refund order</th></tr>{line_rows}</table></div>"
            + events_table(events)
            + f"<div class='card'><h3>Full data (as sent by the POS)</h3><pre>{esc(pretty_json(payload_json))}</pre></div>"
        )
        return self._send(200, page("Pledge return", body, "advances"))

    def _cakes_page(self, params):
        def fields(filters):
            return (
                f"<input name='q' placeholder='Reference / customer / phone / MO' value='{esc(filters['q'])}'>"
                + select_field("state", filters, [("", "Any status"), *CAKE_STATE_LABELS.items()])
                + date_fields(filters)
            )

        def cells(row):
            return (
                f"<td>{order_link(cake_key(row['cake_id']), row['reference'])}</td>"
                f"<td>{esc(row['created_at'] or row['first_seen'])}</td><td>{esc(row['config_name'])}</td>"
                f"<td>{esc(row['cashier'])}</td><td>{esc(row['partner_name'])}</td><td>{esc(row['partner_phone'])}</td>"
                f"<td>{esc(row['size_name'])}</td><td>{esc(row['pieces'])}</td><td>{_money(row['final_price'])}</td>"
                f"<td>{cake_state_badge(row['cake_state'])}</td>"
                f"<td>{order_link(row['pos_order_uuid'], row['order_ref'] or ('order' if row['pos_order_uuid'] else ''))}</td>"
                f"<td>{esc(row['production_name'])}</td>"
            )

        return self._list_page(
            "cakes", "/cakes", params, ("q", "state", "date_from", "date_to"), fields,
            ["Reference", "Ordered", "Register", "Cashier", "Customer", "Phone", "Size", "Pieces", "Final price",
             "Status", "POS order", "Manufacturing order"],
            cells, "Special cakes", "cakes",
        )

    def _cake_page(self, params):
        cake_id = _integer(params.get("id"))
        cake, events, history = self.db.get_cake(cake_id) if cake_id is not None else (None, [], [])
        if cake is None:
            return self._send(404, page("Cake", "<p>Cake order not found.</p>", "cakes"))
        info = [
            ("Reference", esc(cake["reference"])), ("Odoo ID", esc(cake["cake_id"])),
            ("Status", cake_state_badge(cake["cake_state"])), ("Register", esc(cake["config_name"])),
            ("Session", esc(cake["session_name"])), ("Cashier", esc(cake["cashier"])),
            ("Customer", esc(cake["partner_name"])), ("Phone", esc(cake["partner_phone"])),
            ("Product", esc(cake["product_name"])), ("Size", esc(cake["size_name"])),
            ("Pieces", esc(cake["pieces"])), ("Sugar paste", yes_no(cake["sugar_paste"])),
            ("Components", esc(cake["components"])), ("Note", esc(cake["note"])),
            ("Cake base cost", _money(cake["cake_base_cost"])), ("Components cost", _money(cake["components_cost"])),
            ("Price before tax", _money(cake["price_before_tax"])), ("Tax", _money(cake["tax_amount"])),
            ("Final price", _money(cake["final_price"])), ("Manufacturing order", esc(cake["production_name"])),
            ("Ordered", esc(cake["created_at"])), ("Saved to pay later", yes_no(cake["pay_later"])),
            ("Loaded for payment", esc(cake["loaded_at"])),
            ("POS order", order_link(cake["pos_order_uuid"], cake["order_ref"] or cake["pos_order_uuid"])),
            ("POS order status", esc(cake["order_state"])), ("Last update", esc(cake["last_update"])),
        ]
        info_rows = "".join(f"<tr><th>{esc(label)}</th><td>{value}</td></tr>" for label, value in info)
        body = (
            f"<div class='card'><table>{info_rows}</table></div>"
            + events_table(events)
            + f"<div class='card'><h3>Full data (as sent by the POS)</h3>{self._history_blocks(history)}</div>"
        )
        return self._send(200, page("Cake", body, "cakes"))

    def _cash_moves_page(self, params):
        def fields(filters):
            return (
                f"<input name='q' placeholder='Reason / cashier' value='{esc(filters['q'])}'>"
                f"<input name='session' placeholder='Session' value='{esc(filters['session'])}'>"
                + select_field("type", filters, [("", "Any type"), *CASH_MOVE_TYPES.items()])
                + select_field("deleted", filters, [("", "Hide deleted"), ("yes", "Deleted only"),
                                                    ("all", "Include deleted")])
                + date_fields(filters)
            )

        def cells(row):
            source = GROUP_VALUE_LABELS[("cash_moves", "source")].get(row["source"], row["source"])
            return (
                f"<td>{order_link(cash_move_key(row['id']), row['ts'])}</td><td>{esc(row['config_name'])}</td>"
                f"<td>{esc(row['session_name'])}</td><td>{esc(CASH_MOVE_TYPES.get(row['move_type'], row['move_type']))}</td>"
                f"<td>{_money(row['amount'])}</td><td>{esc(row['reason'])}</td><td>{esc(row['cashier'])}</td>"
                f"<td>{esc(source)}</td><td>{cash_move_status(row)}</td>"
            )

        return self._list_page(
            "cash_moves", "/cash-moves", params, ("q", "type", "session", "deleted", "date_from", "date_to"), fields,
            ["Time", "Register", "Session", "Type", "Amount", "Reason", "Cashier", "Made from", "Status"],
            cells, "Cash moves", "cash-moves",
            before="<div class='card'>Cash in/out typed on this POS, cash in/out added from the Odoo backend "
                   "(checked every minute while the POS is open) and cash deliveries. Money out is negative.</div>",
        )

    def _cash_move_page(self, params):
        row_id = _integer(params.get("id"))
        row, events = self.db.get_cash_move(row_id) if row_id is not None else (None, [])
        if row is None:
            return self._send(404, page("Cash move", "<p>Cash move not found.</p>", "cash-moves"))
        info = [
            ("Time", esc(row["ts"])), ("Type", esc(CASH_MOVE_TYPES.get(row["move_type"], row["move_type"]))),
            ("Amount", _money(row["amount"])), ("Reason", esc(row["reason"])), ("Name in Odoo", esc(row["name"])),
            ("Register", esc(row["config_name"])), ("Session", esc(row["session_name"])),
            ("Cashier", esc(row["cashier"])),
            ("Made from", esc(GROUP_VALUE_LABELS[("cash_moves", "source")].get(row["source"], row["source"]))),
            ("Available cash at that time", _money(row["available_cash"])),
            ("Odoo cash line ID", esc(row["statement_line_id"])), ("Status", cash_move_status(row)),
            ("Deleted at", esc(row["deleted_at"])), ("Last update", esc(row["last_update"])),
        ]
        info_rows = "".join(f"<tr><th>{esc(label)}</th><td>{value}</td></tr>" for label, value in info)
        body = (
            f"<div class='card'><table>{info_rows}</table></div>"
            + events_table(events)
            + f"<div class='card'><h3>Full data</h3><pre>{esc(pretty_json(row['details_json']))}</pre></div>"
        )
        return self._send(200, page("Cash move", body, "cash-moves"))

    def _logs_page(self, params):
        def fields(filters):
            return (
                f"<input name='q' placeholder='Record / event / message' value='{esc(filters['q'])}'>"
                + select_field("level", filters, [("", "All levels"), ("info", "Info"), ("warning", "Warning"),
                                                  ("error", "Error")])
                + date_fields(filters)
            )

        def cells(row):
            return (
                f"<td>{esc(row['ts'])}</td><td><span class='badge b-{esc(row['level'])}'>{esc(row['level'])}</span></td>"
                f"<td>{esc(row['event'])}</td><td>{order_link(row['order_uuid'], row['order_ref'])}</td>"
                f"<td>{esc(row['message'])}</td>"
            )

        return self._list_page(
            "logs", "/logs", params, ("level", "q", "date_from", "date_to"), fields,
            ["Time", "Level", "Event", "Record", "Message"], cells, "Logs", "logs",
        )

    def _export_page(self):
        body = (
            "<div class='card'><h3>Export</h3>"
            "<form method='get' action='/export/download'>"
            "<p><label><input type='radio' name='scope' value='unsynced' checked> Paid orders not sent to the server</label></p>"
            "<p><label><input type='radio' name='scope' value='session'> One session: </label>"
            "<input name='session' placeholder='Session name or ID'></p>"
            "<p><label><input type='radio' name='scope' value='all'> All orders</label></p>"
            "<p><label><input type='radio' name='scope' value='advances'> Advance orders and pledge returns "
            "(with failed attempts)</label></p>"
            "<p><label><input type='radio' name='scope' value='pledge_returns'> Pledge returns only</label></p>"
            "<p><label><input type='radio' name='scope' value='cakes'> Special cake orders (with failed attempts)</label></p>"
            "<p><label><input type='radio' name='scope' value='cash_moves'> Cash in/out and deliveries "
            "(with refused attempts)</label></p>"
            "<p>Format: <select name='format'><option value='json'>JSON (full data, for recovery)</option>"
            "<option value='csv'>CSV (summary, for Excel)</option></select></p>"
            "<input type='submit' value='Download'></form></div>"
        )
        return self._send(200, page("Export", body, "export"))

    def _download(self, name, params, payload, csv_columns, csv_rows):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if params.get("format") == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(csv_columns)
            for row in csv_rows:
                writer.writerow([row.get(col) for col in csv_columns])
            return self._send(200, "\ufeff" + buffer.getvalue(), "text/csv; charset=utf-8",
                              {"Content-Disposition": f"attachment; filename={name}_{stamp}.csv"})
        data = json.dumps({"exported_at": _now(), **payload}, ensure_ascii=False, indent=2, default=str)
        return self._send(200, data, "application/json; charset=utf-8",
                          {"Content-Disposition": f"attachment; filename={name}_{stamp}.json"})

    def _export_download(self, params):
        scope = params.get("scope") or "unsynced"
        if scope in ("advances", "pledge_returns"):
            return self._export_advances(params, pledge_returns_only=scope == "pledge_returns")
        if scope == "cakes":
            cakes, failed = self.db.export_cakes()
            self.db.log("info", "export", f"scope=cakes cakes={len(cakes)} failed={len(failed)}")
            return self._download(
                "pos_cakes", params, {"scope": scope, "cakes": cakes, "failed_attempts": failed},
                ["reference", "cake_id", "cake_state", "created_at", "config_name", "session_name", "cashier",
                 "partner_name", "partner_phone", "product_name", "size_name", "pieces", "sugar_paste", "components",
                 "note", "price_before_tax", "tax_amount", "final_price", "production_name", "pay_later",
                 "loaded_at", "order_ref", "order_state"],
                cakes,
            )
        if scope == "cash_moves":
            moves, failed = self.db.export_cash_moves()
            self.db.log("info", "export", f"scope=cash_moves moves={len(moves)} failed={len(failed)}")
            return self._download(
                "pos_cash_moves", params, {"scope": scope, "cash_moves": moves, "failed_attempts": failed},
                ["ts", "move_type", "amount", "reason", "name", "config_name", "session_name", "cashier", "source",
                 "available_cash", "statement_line_id", "queued_offline", "deleted", "deleted_at"],
                moves,
            )
        orders = self.db.export_orders(scope, params.get("session"))
        self.db.log("info", "export", f"scope={scope} session={params.get('session') or '-'} orders={len(orders)}")
        return self._download(
            f"pos_orders_{scope}", params, {"scope": scope, "orders": orders},
            ["pos_reference", "name", "date_order", "config_name", "session_name", "partner_name", "cashier", "state",
             "fiscal_position", "amount_total", "amount_tax", "amount_paid", "amount_return", "synced_to_server",
             "server_id", "deleted", "source", "uuid"],
            orders,
        )

    def _export_advances(self, params, pledge_returns_only=False):
        advances, failed, pledge_returns = self.db.export_advances()
        scope = "pledge_returns" if pledge_returns_only else "advances"
        if pledge_returns_only:
            advances = []
            failed = [event for event in failed if event and event.get("action") == "pledge_return_failed"]
        self.db.log(
            "info", "export",
            f"scope={scope} advances={len(advances)} pledge_returns={len(pledge_returns)} failed={len(failed)}",
        )
        if pledge_returns_only:
            columns = ["ts", "config_name", "session_name", "cashier", "partner_name", "partner_phone",
                       "pledge_count", "total_amount", "payment_method_name", "refund_orders", "origin_orders",
                       "return_move_name"]
            rows = pledge_returns
        else:
            columns = ["reference", "advance_id", "state", "created_at", "config_name", "session_name", "cashier",
                       "partner_name", "partner_phone", "amount_total", "advance_amount", "payment_method_name",
                       "completed_at", "completion_order_ref", "remaining_paid", "completion_payment_method",
                       "refunded_at", "refund_amount", "refund_payment_method"]
            rows = advances
        return self._download(
            f"pos_{scope}", params,
            {"scope": scope, "advances": advances, "pledge_returns": pledge_returns, "failed_attempts": failed},
            columns, rows,
        )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def is_admin():
    if not IS_WINDOWS:
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def require_admin():
    if not is_admin():
        raise SystemExit("Please run this command from a terminal opened 'As Administrator'.")


def ask_secret(label, min_length):
    while True:
        first = getpass.getpass(f"{label}: ")
        if len(first) < min_length:
            print(f"  Must be at least {min_length} characters.")
            continue
        if getpass.getpass(f"Repeat {label.lower()}: ") != first:
            print("  The two values do not match, try again.")
            continue
        return first


def open_db(config):
    return BackupDB(db_path(), unprotect_secret(config["db_key"]), config.get("allow_unencrypted"))


def cmd_setup(args):
    require_admin()
    if os.path.exists(config_path()) and not args.force:
        raise SystemExit("Already configured. Use change-pin / change-db-password, or 'setup --force' to start over.")
    if os.path.exists(db_path()) and args.force:
        raise SystemExit(f"A database already exists at {db_path()}. Move it away before running setup --force.")
    if sqlcipher is None and not args.allow_unencrypted:
        raise SystemExit("sqlcipher3 is not available in this build; the database cannot be encrypted.")

    print(f"{APP_TITLE} - setup\n")
    origins = input(
        "Odoo website address(es), comma separated\n"
        "  e.g. https://anabtawi-group.odoo.com, https://*.dev.odoo.com\n> "
    )
    allowed = [o.strip().rstrip("/") for o in origins.split(",") if o.strip()]
    if not allowed:
        raise SystemExit("At least one Odoo address is required.")
    port = input("Port [8765]: ").strip() or "8765"
    pin = ask_secret("Manager PIN for the logs screen", 4)
    db_password = ask_secret("Database password", 8)

    config = dict(DEFAULT_CONFIG)
    config.update(
        port=int(port),
        allowed_origins=allowed,
        api_key=secrets.token_urlsafe(24),
        admin_pin_hash=hash_pin(pin),
        db_key=protect_secret(db_password),
        allow_unencrypted=bool(args.allow_unencrypted),
    )
    save_config(config)
    db = open_db(config)
    db.log("info", "setup", "helper configured")
    restrict_data_dir()

    print("\nSetup complete.")
    print(f"  Data folder : {data_dir()}")
    print(f"  Logs screen : http://127.0.0.1:{config['port']}/")
    print("\nEnter these values in Odoo (Point of Sale > Configuration > Point of Sales > Local SQL Backup):")
    print(f"  Helper URL  : http://127.0.0.1:{config['port']}")
    print(f"  API key     : {config['api_key']}")
    print("\nKeep the database password somewhere safe: it is needed to open the database with other tools.")


def cmd_run(_args):
    config = load_config()
    db = open_db(config)
    server = HelperServer(("127.0.0.1", int(config["port"])), config, db)
    db.log("info", "service_started", f"version {VERSION}, port {config['port']}, encrypted={db.encrypted}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        db.log("info", "service_stopped", "")
        server.server_close()


def _executable_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def cmd_install_startup(_args):
    require_admin()
    if not IS_WINDOWS:
        raise SystemExit("install-startup is only available on Windows.")
    config = load_config()
    command = f"{_executable_command()} run"
    subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", command, "/SC", "ONSTART",
         "/RU", "SYSTEM", "/RL", "HIGHEST", "/F"],
        check=True,
    )
    subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], check=False)
    public_desktop = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")
    if os.path.isdir(public_desktop):
        with open(os.path.join(public_desktop, "POS Local Backup.url"), "w", encoding="utf-8") as handle:
            handle.write(f"[InternetShortcut]\nURL=http://127.0.0.1:{config['port']}/\n")
    print("The helper now starts automatically with Windows and is running.")


def cmd_uninstall_startup(_args):
    require_admin()
    subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], check=False)
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False)
    print("Startup task removed. The database and logs were kept.")


def cmd_change_pin(_args):
    require_admin()
    config = load_config()
    config["admin_pin_hash"] = hash_pin(ask_secret("New manager PIN", 4))
    save_config(config)
    open_db(config).log("info", "pin_changed", "manager PIN changed")
    print("PIN changed. Restart the helper (or the PC) to apply it.")


def cmd_change_db_password(_args):
    require_admin()
    config = load_config()
    if getpass.getpass("Current database password: ") != unprotect_secret(config["db_key"]):
        raise SystemExit("Wrong current password.")
    new_password = ask_secret("New database password", 8)
    if IS_WINDOWS:
        subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], check=False, capture_output=True)
    db = open_db(config)
    db.rekey(new_password)
    config["db_key"] = protect_secret(new_password)
    save_config(config)
    db.log("info", "db_password_changed", "database re-encrypted with a new password")
    if IS_WINDOWS:
        subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], check=False, capture_output=True)
    print("Database password changed.")


def cmd_show_config(_args):
    require_admin()
    config = load_config()
    print(f"Helper URL      : http://127.0.0.1:{config['port']}")
    print(f"API key         : {config['api_key']}")
    print(f"Allowed origins : {', '.join(config['allowed_origins'])}")
    print(f"Data folder     : {data_dir()}")


def main():
    parser = argparse.ArgumentParser(description=APP_TITLE)
    sub = parser.add_subparsers(dest="command", required=True)
    setup_parser = sub.add_parser("setup", help="first-time configuration")
    setup_parser.add_argument("--force", action="store_true", help="overwrite an existing configuration")
    setup_parser.add_argument("--allow-unencrypted", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("run", help="start the service")
    sub.add_parser("install-startup", help="start automatically with Windows")
    sub.add_parser("uninstall-startup", help="remove the startup task")
    sub.add_parser("change-pin", help="change the manager PIN")
    sub.add_parser("change-db-password", help="change the database password")
    sub.add_parser("show-config", help="show the values to enter in Odoo")
    args = parser.parse_args()

    os.makedirs(data_dir(), exist_ok=True)
    setup_logging(to_console=args.command != "run")
    commands = {
        "setup": cmd_setup,
        "run": cmd_run,
        "install-startup": cmd_install_startup,
        "uninstall-startup": cmd_uninstall_startup,
        "change-pin": cmd_change_pin,
        "change-db-password": cmd_change_db_password,
        "show-config": cmd_show_config,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
