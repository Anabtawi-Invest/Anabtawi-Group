# ZK Bridge Agent Example

Run this script on a machine inside the same network as the biometric device.

## Requirements

- Python 3
- `pip install pyzk requests`

## Environment Variables

- `ODOO_URL`: Your Odoo base URL, for example `https://my-db.odoo.com`
- `BRIDGE_TOKEN`: Token copied from the `Bridge Devices` form in Odoo
- `DEVICE_IP`: Device IP on the local network
- `DEVICE_PORT`: Device SDK port, for example `4372`
- `DEVICE_IDENTIFIER`: Optional external device code
- `DEVICE_TIMEZONE`: Device local timezone, for example `Asia/Amman`
- `DEVICE_PASSWORD`: Optional communication password, default `0`
- `DEVICE_TIMEOUT`: Optional timeout in seconds, default `30`

## Example

```bash
export ODOO_URL="https://my-db.odoo.com"
export BRIDGE_TOKEN="paste-token-here"
export DEVICE_IP="192.168.100.64"
export DEVICE_PORT="4372"
export DEVICE_TIMEZONE="Asia/Amman"
python3 zk_bridge_agent.py
```

The server deduplicates punches, so sending the same logs more than once is safe.
