#!/usr/bin/env bash
set -euo pipefail

# You can override this when running:
# ODOO_URL="https://your-domain.odoo.com" bash run_3_devices.sh
ODOO_URL="${ODOO_URL:-https://anabtawi-group.odoo.com}"
DEVICE_TIMEZONE="${DEVICE_TIMEZONE:-Asia/Amman}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
AGENT_SCRIPT="${AGENT_SCRIPT:-zk_bridge_agent.py}"

run_device() {
  local identifier="$1"
  local token="$2"
  local ip="$3"
  local port="$4"

  echo "=================================================="
  echo "Syncing ${identifier} (${ip}:${port})"
  echo "=================================================="

  ODOO_URL="${ODOO_URL}" \
  BRIDGE_TOKEN="${token}" \
  DEVICE_IP="${ip}" \
  DEVICE_PORT="${port}" \
  DEVICE_IDENTIFIER="${identifier}" \
  DEVICE_TIMEZONE="${DEVICE_TIMEZONE}" \
  "${PYTHON_BIN}" "${AGENT_SCRIPT}"
}

# Device 1
run_device \
  "zkteco_factory_3" \
  "85DufQu8-VdcIIjEbY-N3mIu9tO7jLrI" \
  "192.168.3.51" \
  "4371"

# Device 2
run_device \
  "zkteco_factory_2" \
  "6OsaQMr-K_pJf2niT-g40_z0_gUJZXMU" \
  "192.168.3.54" \
  "4372"

# Device 3
run_device \
  "zkteco_factory_4" \
  "vWSbWz7Lkyhl1CMCxbxLMDyMwciSIgwP" \
  "192.168.3.201" \
  "4373"

echo "All devices sync finished."
