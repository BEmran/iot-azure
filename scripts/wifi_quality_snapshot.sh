#!/usr/bin/env bash
set -euo pipefail

# Wi-Fi snapshot:
# - Captures SSID/RSSI/bitrate
# - Captures station dump (retries, tx/rx, signal)
# - Pings gateway + 1.1.1.1 for loss/jitter
#
# Usage:
#   ./wifi_quality_snapshot.sh
#   ./wifi_quality_snapshot.sh -I wlan0 -c 30

IFACE="wlan0"
PING_COUNT=20
PING_TIMEOUT=1
LOG_DIR="./logs"

while getopts ":I:c:W:h" opt; do
  case "$opt" in
    I) IFACE="$OPTARG" ;;
    c) PING_COUNT="$OPTARG" ;;
    W) PING_TIMEOUT="$OPTARG" ;;
    h)
      echo "Usage: $0 [-I <wifi_iface>] [-c ping_count] [-W ping_timeout_sec]"
      exit 0
      ;;
    \?) echo "Unknown option: -$OPTARG" >&2; exit 2 ;;
    :)  echo "Missing argument for -$OPTARG" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"
TS="$(date +"%Y%m%d_%H%M%S")"
OUT="${LOG_DIR}/wifi_snapshot_${TS}.txt"
exec > >(tee -a "$OUT") 2>&1

echo "=== Wi-Fi Quality Snapshot ==="
echo "Timestamp: $(date)"
echo "Host: $(hostname)  User: $(whoami)"
echo "Interface: ${IFACE}"
echo

echo "== IP / Route context =="
ip -br addr || true
echo
ip route || true
echo

GATEWAY="$(ip route | awk '/default/ {print $3; exit}' || true)"
echo "Default gateway: ${GATEWAY:-UNKNOWN}"
echo

echo "== Wi-Fi link (iw) =="
if command -v iw >/dev/null 2>&1; then
  iw dev "$IFACE" link || true
  echo
  echo "== Wi-Fi station dump (AP link stats) =="
  # Shows signal, tx/rx bitrate, retries, etc.
  iw dev "$IFACE" station dump || true
  echo
else
  echo "iw not found. Install: sudo apt install iw"
fi

echo "== NetworkManager snapshot (nmcli) =="
if command -v nmcli >/dev/null 2>&1; then
  nmcli -f GENERAL.CONNECTION,GENERAL.DEVICE,GENERAL.STATE dev show "$IFACE" || true
  echo
  nmcli -t -f IN-USE,SSID,SIGNAL,RATE,CHAN,BARS dev wifi list ifname "$IFACE" || true
  echo
fi

echo "== Latency / loss checks =="
if command -v ping >/dev/null 2>&1; then
  if [[ -n "${GATEWAY}" ]]; then
    echo "-- Ping gateway (${GATEWAY})"
    ping -c "$PING_COUNT" -W "$PING_TIMEOUT" "$GATEWAY" || true
    echo
  fi
  echo "-- Ping public DNS (1.1.1.1)"
  ping -c "$PING_COUNT" -W "$PING_TIMEOUT" 1.1.1.1 || true
else
  echo "ping not found. Install: sudo apt install iputils-ping"
fi

echo
echo "=== Done. Log saved to: ${OUT} ==="
