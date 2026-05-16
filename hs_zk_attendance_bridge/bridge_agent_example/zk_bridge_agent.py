#!/usr/bin/env python3
"""Simple local bridge agent for ZK devices.

Run this script on a machine that can reach the biometric device over LAN.
It fetches attendance logs using pyzk and pushes them to Odoo.sh.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import timezone

import requests
from zk import ZK


def getenv(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def load_devices(default_token: str = "") -> list[dict]:
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
                    "identifier": (device.get("identifier") or device.get("device_identifier") or device_ip),
                    "token": device_token,
                    "timezone": device.get("timezone", ""),
                    "password": int(device.get("password", 0)),
                    "timeout": int(device.get("timeout", 30)),
                }
            )
        return devices

    # Legacy single-device mode
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


def sync_device(odoo_url: str, device: dict) -> dict:
    zk_client = ZK(
        device["ip"],
        port=device["port"],
        timeout=device["timeout"],
        password=device["password"],
        force_udp=False,
        ommit_ping=False,
    )

    connection = None
    try:
        connection = zk_client.connect()
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
                    "device_timezone": device["timezone"],
                }
            )
    finally:
        if connection is not None:
            try:
                connection.disconnect()
            except Exception:
                pass

    payload = {
        "token": device["token"],
        "device_identifier": device["identifier"],
        "source": "zk_bridge_agent",
        "records": records,
    }
    response = requests.post(
        f"{odoo_url}/hs_zk_attendance_bridge/push",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    odoo_url = getenv("ODOO_URL", required=True).rstrip("/")
    bridge_token = getenv("BRIDGE_TOKEN", "")
    devices = load_devices(bridge_token)

    results = []
    failures = []
    for device in devices:
        try:
            result = sync_device(odoo_url, device)
            results.append({"device_identifier": device["identifier"], "response": result})
        except Exception as exc:
            failures.append({"device_identifier": device["identifier"], "error": str(exc)})

    print(json.dumps({"results": results, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    run_once = getenv("RUN_ONCE", "0").strip().lower() in {"1", "true", "yes"}
    sync_interval = int(getenv("SYNC_INTERVAL", "60"))

    if run_once:
        try:
            raise SystemExit(main())
        except Exception as exc:
            print(f"Bridge sync failed: {exc}", file=sys.stderr)
            raise SystemExit(1)

    try:
        while True:
            try:
                exit_code = main()
                if exit_code != 0:
                    print(f"Sync cycle finished with exit code {exit_code}", file=sys.stderr)
            except Exception as exc:
                print(f"Bridge sync failed: {exc}", file=sys.stderr)

            print(f"Waiting {sync_interval} seconds before next sync...")
            time.sleep(sync_interval)
    except KeyboardInterrupt:
        print("Stopped by user")
        raise SystemExit(0)
