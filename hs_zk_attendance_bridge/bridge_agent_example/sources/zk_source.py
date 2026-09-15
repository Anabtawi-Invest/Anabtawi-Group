# -*- coding: utf-8 -*-
"""ZK device attendance source (existing pyzk flow)."""

from __future__ import annotations

import json
import logging
from datetime import timezone

from config_utils import getenv

_logger = logging.getLogger(__name__)


def _import_zk():
    try:
        from zk import ZK
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency pyzk. Install with: pip install pyzk"
        ) from exc
    return ZK


def load_zk_devices(default_token: str = "") -> list[dict]:
    """Load devices from DEVICES_JSON or fallback to legacy single-device env vars."""
    devices_json = getenv("DEVICES_JSON", "").strip()
    if devices_json:
        parsed = json.loads(devices_json)
        if not isinstance(parsed, list) or not parsed:
            raise RuntimeError("DEVICES_JSON must be a non-empty JSON list")

        devices = []
        for index, device in enumerate(parsed, start=1):
            if not isinstance(device, dict):
                raise RuntimeError(f"Device #{index} must be a JSON object")

            device_ip = (device.get("ip") or device.get("device_ip") or "").strip()
            if not device_ip:
                raise RuntimeError(f"Device #{index} is missing 'ip'")

            device_token = (device.get("token") or default_token).strip()
            if not device_token:
                raise RuntimeError(
                    f"Device #{index} is missing 'token' and BRIDGE_TOKEN is not set"
                )

            devices.append(
                {
                    "ip": device_ip,
                    "port": int(device.get("port", 4370)),
                    "identifier": (
                        device.get("identifier")
                        or device.get("device_identifier")
                        or device_ip
                    ),
                    "token": device_token,
                    "timezone": device.get("timezone", ""),
                    "password": int(device.get("password", 0)),
                    "timeout": int(device.get("timeout", 30)),
                }
            )
        return devices

    device_ip = getenv("DEVICE_IP", required=True)
    return [
        {
            "ip": device_ip,
            "port": int(getenv("DEVICE_PORT", "4370")),
            "identifier": getenv("DEVICE_IDENTIFIER", device_ip),
            "token": getenv("BRIDGE_TOKEN", required=True),
            "timezone": getenv("DEVICE_TIMEZONE", ""),
            "password": int(getenv("DEVICE_PASSWORD", "0")),
            "timeout": int(getenv("DEVICE_TIMEOUT", "30")),
        }
    ]


class ZkAttendanceSource:
    """Reads all punches from one ZK device and normalizes them for Odoo."""

    source_name = "zk_bridge_agent"

    def __init__(self, device: dict):
        self.device = device

    def fetch_batches(self) -> list[dict]:
        ZK = _import_zk()
        zk_client = ZK(
            self.device["ip"],
            port=self.device["port"],
            timeout=self.device["timeout"],
            password=self.device["password"],
            force_udp=False,
            ommit_ping=False,
        )

        connection = None
        records = []
        try:
            _logger.info(
                "Connecting to ZK device %s (%s:%s)",
                self.device["identifier"],
                self.device["ip"],
                self.device["port"],
            )
            connection = zk_client.connect()
            connection.disable_device()
            for attendance in connection.get_attendance():
                punch_time = attendance.timestamp
                if punch_time.tzinfo:
                    punch_time = punch_time.astimezone(timezone.utc).replace(tzinfo=None)
                records.append(
                    {
                        "device_user_id": str(attendance.user_id),
                        "punch_time": punch_time.isoformat(),
                        "punch_type": "",
                        "device_timezone": self.device["timezone"],
                    }
                )
        finally:
            if connection is not None:
                try:
                    connection.disconnect()
                except Exception:
                    pass

        _logger.info(
            "Found %s attendance records on ZK device %s",
            len(records),
            self.device["identifier"],
        )
        return [
            {
                "token": self.device["token"],
                "device_identifier": self.device["identifier"],
                "records": records,
                "cursor": None,
            }
        ]
