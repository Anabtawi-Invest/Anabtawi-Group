#!/usr/bin/env python3
"""Simple local bridge agent for ZK devices.

Run this script on a machine that can reach the biometric device over LAN.
It fetches attendance logs using pyzk and pushes them to Odoo.sh.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timezone

import requests
from zk import ZK


def getenv(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def main() -> int:
    odoo_url = getenv("ODOO_URL", required=True).rstrip("/")
    bridge_token = getenv("BRIDGE_TOKEN", required=True)
    device_ip = getenv("DEVICE_IP", required=True)
    device_port = int(getenv("DEVICE_PORT", "4370"))
    device_identifier = getenv("DEVICE_IDENTIFIER", device_ip)
    device_password = int(getenv("DEVICE_PASSWORD", "0"))
    timeout = int(getenv("DEVICE_TIMEOUT", "30"))

    zk_client = ZK(
        device_ip,
        port=device_port,
        timeout=timeout,
        password=device_password,
        force_udp=False,
        ommit_ping=False,
    )

    connection = zk_client.connect()
    try:
        connection.disable_device()
        records = []
        for attendance in connection.get_attendance():
            punch_time = attendance.timestamp
            if punch_time.tzinfo:
                punch_time = punch_time.astimezone(timezone.utc).replace(tzinfo=None)
            records.append(
                {
                    "device_user_id": str(attendance.user_id),
                    "punch_time": punch_time.isoformat(),
                    "punch_type": "",
                }
            )
    finally:
        try:
            connection.disconnect()
        except Exception:
            pass

    payload = {
        "token": bridge_token,
        "device_identifier": device_identifier,
        "source": "zk_bridge_agent",
        "records": records,
    }
    response = requests.post(
        f"{odoo_url}/hs_zk_attendance_bridge/push",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Bridge sync failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
