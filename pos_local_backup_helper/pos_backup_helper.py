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
VERSION = "1.0.0"
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
"""

ORDER_COLUMNS = [
    "pos_reference", "name", "config_id", "config_name", "session_id", "session_name",
    "date_order", "partner_id", "partner_name", "cashier", "state", "amount_total",
    "amount_tax", "amount_paid", "amount_return",
]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sql_quote(value):
    return "'" + value.replace("'", "''") + "'"


class BackupDB:
    def __init__(self, path, password, allow_unencrypted=False):
        self.path = path
        self.lock = threading.RLock()
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
            self.conn.executescript(SCHEMA)
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
        values["synced_to_server"] = 1 if server_id else 0
        values["server_id"] = server_id
        values["payload_json"] = json.dumps(order.get("payload"), ensure_ascii=False, default=str)
        values["last_update"] = _now()

        existing = self.conn.execute(
            "SELECT state, amount_total, server_id, deleted FROM pos_order WHERE uuid = ?", (uuid,)
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
                f"state={values['state']} total={values['amount_total']}",
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
        return {
            "total": row["total"] or 0,
            "unsynced": row["unsynced"] or 0,
            "open_orders": row["open_orders"] or 0,
            "deleted": row["deleted"] or 0,
            "last_update": row["last_update"] or "-",
            "errors_24h": errors,
        }

    def _order_filters(self, filters):
        clauses, params = [], []
        if filters.get("q"):
            clauses.append("(pos_reference LIKE ? OR name LIKE ? OR partner_name LIKE ?)")
            params += [f"%{filters['q']}%"] * 3
        if filters.get("state"):
            clauses.append("state = ?")
            params.append(filters["state"])
        if filters.get("session"):
            clauses.append("(session_name LIKE ? OR CAST(session_id AS TEXT) = ?)")
            params += [f"%{filters['session']}%", filters["session"]]
        if filters.get("synced") == "no":
            clauses.append("synced_to_server = 0")
        elif filters.get("synced") == "yes":
            clauses.append("synced_to_server = 1")
        if filters.get("deleted") == "yes":
            clauses.append("deleted = 1")
        elif filters.get("deleted") != "all":
            clauses.append("deleted = 0")
        if filters.get("date_from"):
            clauses.append("date_order >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            clauses.append("date_order <= ?")
            params.append(filters["date_to"] + " 23:59:59")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def list_orders(self, filters, page=1):
        where, params = self._order_filters(filters)
        with self.lock:
            total = self.conn.execute(f"SELECT COUNT(*) FROM pos_order{where}", params).fetchone()[0]
            rows = self.conn.execute(
                f"SELECT * FROM pos_order{where} ORDER BY date_order DESC, last_update DESC LIMIT ? OFFSET ?",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            ).fetchall()
        return total, rows

    def get_order(self, uuid):
        with self.lock:
            order = self.conn.execute("SELECT * FROM pos_order WHERE uuid = ?", (uuid,)).fetchone()
            lines = self.conn.execute("SELECT * FROM pos_order_line WHERE order_uuid = ?", (uuid,)).fetchall()
            payments = self.conn.execute("SELECT * FROM pos_payment WHERE order_uuid = ?", (uuid,)).fetchall()
            events = self.conn.execute(
                "SELECT * FROM event_log WHERE order_uuid = ? ORDER BY id DESC", (uuid,)
            ).fetchall()
        return order, lines, payments, events

    def list_logs(self, filters, page=1):
        clauses, params = [], []
        if filters.get("level"):
            clauses.append("level = ?")
            params.append(filters["level"])
        if filters.get("q"):
            clauses.append("(order_ref LIKE ? OR message LIKE ? OR event LIKE ?)")
            params += [f"%{filters['q']}%"] * 3
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.lock:
            total = self.conn.execute(f"SELECT COUNT(*) FROM event_log{where}", params).fetchone()[0]
            rows = self.conn.execute(
                f"SELECT * FROM event_log{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, PAGE_SIZE, (page - 1) * PAGE_SIZE],
            ).fetchall()
        return total, rows

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
"""

TABS = [("status", "Status"), ("orders", "Orders"), ("logs", "Logs"), ("export", "Export")]


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
    return badges


def order_link(uuid, label):
    if not uuid:
        return ""
    return f"<a href='/order?uuid={esc(uuid)}'>{esc(label or uuid)}</a>"


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

    def _orders_page(self, params):
        page_number = max(1, int(params.get("page") or 1))
        filters = {k: params.get(k, "") for k in ("q", "state", "session", "synced", "deleted", "date_from", "date_to")}
        total, rows = self.db.list_orders(filters, page_number)

        def option(name, value, label):
            selected = " selected" if filters.get(name) == value else ""
            return f"<option value='{value}'{selected}>{label}</option>"

        form = (
            "<form class='filters card' method='get' action='/orders'>"
            f"<input name='q' placeholder='Reference / customer' value='{esc(filters['q'])}'>"
            f"<input name='session' placeholder='Session' value='{esc(filters['session'])}'>"
            "<select name='state'>" + option("state", "", "Any status") + option("state", "draft", "New (draft)")
            + option("state", "paid", "Paid") + option("state", "done", "Posted") + option("state", "cancel", "Cancelled")
            + "</select><select name='synced'>" + option("synced", "", "Sent to server?")
            + option("synced", "no", "Not sent") + option("synced", "yes", "Sent") + "</select>"
            "<select name='deleted'>" + option("deleted", "", "Hide deleted") + option("deleted", "yes", "Deleted only")
            + option("deleted", "all", "Include deleted") + "</select>"
            f"<input type='date' name='date_from' value='{esc(filters['date_from'])}'>"
            f"<input type='date' name='date_to' value='{esc(filters['date_to'])}'>"
            "<input type='submit' value='Search'></form>"
        )
        rows_html = "".join(
            "<tr>"
            f"<td>{order_link(row['uuid'], row['pos_reference'] or row['name'])}</td>"
            f"<td>{esc(row['date_order'])}</td><td>{esc(row['config_name'])}</td><td>{esc(row['session_name'])}</td>"
            f"<td>{esc(row['partner_name'])}</td><td>{esc(row['cashier'])}</td>"
            f"<td>{state_badges(row)}</td>"
            f"<td>{row['amount_total'] or 0:.3f}</td><td>{row['amount_paid'] or 0:.3f}</td>"
            f"<td>{yes_no(row['synced_to_server'])}</td><td>{esc(row['last_update'])}</td>"
            "</tr>"
            for row in rows
        )
        table = (
            "<table><tr><th>Reference</th><th>Date</th><th>Register</th><th>Session</th><th>Customer</th>"
            "<th>Cashier</th><th>Status</th><th>Total</th><th>Paid</th><th>On server</th><th>Last update</th></tr>"
            f"{rows_html}</table>"
        )
        body = form + "<div class='card'>" + pager("/orders", filters, page_number, total) + table + "</div>"
        return self._send(200, page("Orders", body, "orders"))

    def _order_page(self, params):
        order, lines, payments, events = self.db.get_order(params.get("uuid", ""))
        if order is None:
            return self._send(404, page("Order", "<p>Order not found.</p>", "orders"))
        info_rows = "".join(
            f"<tr><th>{esc(label)}</th><td>{esc(order[key])}</td></tr>"
            for label, key in [
                ("Reference", "pos_reference"), ("Order name", "name"), ("UUID", "uuid"), ("Register", "config_name"),
                ("Session", "session_name"), ("Date", "date_order"), ("Customer", "partner_name"),
                ("Cashier", "cashier"), ("Status", "state"), ("Total", "amount_total"), ("Tax", "amount_tax"),
                ("Paid", "amount_paid"), ("Change", "amount_return"), ("Server ID", "server_id"),
                ("First seen", "first_seen"), ("Last update", "last_update"), ("Deleted at", "deleted_at"),
            ]
        )
        line_rows = "".join(
            f"<tr><td>{esc(line['product_name'])}</td><td>{esc(line['qty'])}</td><td>{esc(line['price_unit'])}</td>"
            f"<td>{esc(line['discount'])}</td><td>{esc(line['price_subtotal'])}</td><td>{esc(line['price_subtotal_incl'])}</td></tr>"
            for line in lines
        )
        payment_rows = "".join(
            f"<tr><td>{esc(p['payment_method_name'])}</td><td>{esc(p['amount'])}</td><td>{esc(p['payment_date'])}</td></tr>"
            for p in payments
        )
        event_rows = "".join(
            f"<tr><td>{esc(e['ts'])}</td><td><span class='badge b-{esc(e['level'])}'>{esc(e['level'])}</span></td>"
            f"<td>{esc(e['event'])}</td><td>{esc(e['message'])}</td></tr>"
            for e in events
        )
        try:
            payload = json.dumps(json.loads(order["payload_json"] or "null"), indent=2, ensure_ascii=False)
        except ValueError:
            payload = order["payload_json"]
        body = (
            f"<div class='card'><table>{info_rows}<tr><th>On server</th><td>{yes_no(order['synced_to_server'])}</td></tr></table></div>"
            "<div class='card'><h3>Lines</h3><table><tr><th>Product</th><th>Qty</th><th>Unit price</th><th>Discount %</th>"
            f"<th>Subtotal</th><th>Subtotal incl. tax</th></tr>{line_rows}</table></div>"
            f"<div class='card'><h3>Payments</h3><table><tr><th>Method</th><th>Amount</th><th>Date</th></tr>{payment_rows}</table></div>"
            f"<div class='card'><h3>Events</h3><table><tr><th>Time</th><th>Level</th><th>Event</th><th>Message</th></tr>{event_rows}</table></div>"
            f"<div class='card'><h3>Full data (as stored by the browser)</h3><pre>{esc(payload)}</pre></div>"
        )
        return self._send(200, page("Order", body, "orders"))

    def _logs_page(self, params):
        page_number = max(1, int(params.get("page") or 1))
        filters = {k: params.get(k, "") for k in ("level", "q")}
        total, rows = self.db.list_logs(filters, page_number)
        levels = "".join(
            f"<option value='{value}'{' selected' if filters['level'] == value else ''}>{label}</option>"
            for value, label in [("", "All levels"), ("info", "Info"), ("warning", "Warning"), ("error", "Error")]
        )
        form = (
            "<form class='filters card' method='get' action='/logs'>"
            f"<input name='q' placeholder='Order / event / message' value='{esc(filters['q'])}'>"
            f"<select name='level'>{levels}</select><input type='submit' value='Search'></form>"
        )
        rows_html = "".join(
            f"<tr><td>{esc(row['ts'])}</td><td><span class='badge b-{esc(row['level'])}'>{esc(row['level'])}</span></td>"
            f"<td>{esc(row['event'])}</td>"
            f"<td>{order_link(row['order_uuid'], row['order_ref'])}</td>"
            f"<td>{esc(row['message'])}</td></tr>"
            for row in rows
        )
        table = (
            "<table><tr><th>Time</th><th>Level</th><th>Event</th><th>Order</th><th>Message</th></tr>"
            f"{rows_html}</table>"
        )
        body = form + "<div class='card'>" + pager("/logs", filters, page_number, total) + table + "</div>"
        return self._send(200, page("Logs", body, "logs"))

    def _export_page(self):
        body = (
            "<div class='card'><h3>Export orders</h3>"
            "<form method='get' action='/export/download'>"
            "<p><label><input type='radio' name='scope' value='unsynced' checked> Paid orders not sent to the server</label></p>"
            "<p><label><input type='radio' name='scope' value='session'> One session: </label>"
            "<input name='session' placeholder='Session name or ID'></p>"
            "<p><label><input type='radio' name='scope' value='all'> All orders</label></p>"
            "<p>Format: <select name='format'><option value='json'>JSON (full data, for recovery)</option>"
            "<option value='csv'>CSV (summary, for Excel)</option></select></p>"
            "<input type='submit' value='Download'></form></div>"
        )
        return self._send(200, page("Export", body, "export"))

    def _export_download(self, params):
        scope = params.get("scope") or "unsynced"
        orders = self.db.export_orders(scope, params.get("session"))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.db.log("info", "export", f"scope={scope} session={params.get('session') or '-'} orders={len(orders)}")
        if params.get("format") == "csv":
            buffer = io.StringIO()
            columns = ["pos_reference", "name", "date_order", "config_name", "session_name", "partner_name",
                       "cashier", "state", "amount_total", "amount_tax", "amount_paid", "amount_return",
                       "synced_to_server", "server_id", "deleted", "uuid"]
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for order in orders:
                writer.writerow([order.get(col) for col in columns])
            data = "\ufeff" + buffer.getvalue()
            return self._send(200, data, "text/csv; charset=utf-8",
                              {"Content-Disposition": f"attachment; filename=pos_orders_{scope}_{stamp}.csv"})
        data = json.dumps({"exported_at": _now(), "scope": scope, "orders": orders}, ensure_ascii=False, indent=2)
        return self._send(200, data, "application/json; charset=utf-8",
                          {"Content-Disposition": f"attachment; filename=pos_orders_{scope}_{stamp}.json"})


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
