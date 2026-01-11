#!/usr/bin/env bash
set -euo pipefail

# Reachability test for Wi-Fi sites:
# - Ping reachability
# - ARP neighbor check (useful when ICMP is blocked)
# - TCP port checks (nc or /dev/tcp)
#
# Usage:
#   ./reachability_test.sh -i 192.168.1.50 -p 80,443
# Optional:
#   ./reachability_test.sh -i 192.168.1.50 -p 80,443 -a   (enable arping)

DEVICE_IP=""
PORTS="80,443"
PING_COUNT=10
PING_TIMEOUT=1
TCP_TIMEOUT=2
DO_ARPING=0
LOG_DIR="./logs"

while getopts ":i:p:c:W:t:ah" opt; do
  case "$opt" in
    i) DEVICE_IP="$OPTARG" ;;
    p) PORTS="$OPTARG" ;;
    c) PING_COUNT="$OPTARG" ;;
    W) PING_TIMEOUT="$OPTARG" ;;
    t) TCP_TIMEOUT="$OPTARG" ;;
    a) DO_ARPING=1 ;;
    h)
      echo "Usage: $0 -i <device_ip> [-p ports_csv] [-c ping_count] [-W ping_timeout_sec] [-t tcp_timeout_sec] [-a]"
      exit 0
      ;;
    \?) echo "Unknown option: -$OPTARG" >&2; exit 2 ;;
    :)  echo "Missing argument for -$OPTARG" >&2; exit 2 ;;
  esac
done

if [[ -z "${DEVICE_IP}" ]]; then
  echo "ERROR: device IP is required. Example: $0 -i 192.168.1.50 -p 80,443" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
TS="$(date +"%Y%m%d_%H%M%S")"
OUT="${LOG_DIR}/reachability_${TS}.txt"
exec > >(tee -a "$OUT") 2>&1

echo "=== Reachability Test (Wi-Fi sites) ==="
echo "Timestamp: $(date)"
echo "Host: $(hostname)  User: $(whoami)"
echo "Device IP: ${DEVICE_IP}"
echo "Ports: ${PORTS}"
echo

echo "== Network context =="
ip -br addr || true
echo
ip route || true
echo

echo "== ARP/Neighbor table snapshot (before tests) =="
ip neigh show | head -n 50 || true
echo

echo "== Ping test =="
ping -c "$PING_COUNT" -W "$PING_TIMEOUT" "$DEVICE_IP" || true
echo

echo "== Neighbor resolution for device IP =="
ip neigh get "$DEVICE_IP" || true
echo

if [[ "$DO_ARPING" -eq 1 ]]; then
  echo "== ARPing test (useful if ICMP ping is blocked) =="
  if command -v arping >/dev/null 2>&1; then
    # arping may require sudo on some systems
    arping -c 3 "$DEVICE_IP" || true
  else
    echo "arping not found. Install: sudo apt install arping"
  fi
  echo
fi

echo "== TCP port tests =="
IFS=',' read -r -a PORT_ARR <<< "$PORTS"

tcp_check_nc() { nc -vz -w "$TCP_TIMEOUT" "$1" "$2"; }

tcp_check_devtcp() {
  local ip="$1" port="$2"
  if command -v timeout >/dev/null 2>&1; then
    timeout "${TCP_TIMEOUT}s" bash -c "cat < /dev/null > /dev/tcp/${ip}/${port}" 2>/dev/null
  else
    bash -c "cat < /dev/null > /dev/tcp/${ip}/${port}" 2>/dev/null
  fi
}

HAS_NC=0; command -v nc >/dev/null 2>&1 && HAS_NC=1

for port in "${PORT_ARR[@]}"; do
  port="$(echo "$port" | xargs)"; [[ -z "$port" ]] && continue
  echo "-- Checking ${DEVICE_IP}:${port}"
  if [[ "$HAS_NC" -eq 1 ]]; then
    tcp_check_nc "$DEVICE_IP" "$port" || echo "FAILED: ${DEVICE_IP}:${port}"
  else
    echo "nc not found, using /dev/tcp fallback..."
    tcp_check_devtcp "$DEVICE_IP" "$port" && echo "OK: ${DEVICE_IP}:${port}" || echo "FAILED: ${DEVICE_IP}:${port}"
  fi
  echo
done

echo "== ARP/Neighbor table snapshot (after tests) =="
ip neigh show | head -n 50 || true
echo

echo "=== Done. Log saved to: ${OUT} ==="
