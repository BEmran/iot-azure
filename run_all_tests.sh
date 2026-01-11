#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------
# Wrapper to run:
#  1) wifi_quality_snapshot.sh
#  2) reachability_test.sh (for one or more devices)
#  3) internet_access_test.sh
#
# Device IPs can be provided:
#  - via -d (CSV list), OR
#  - via -f <file>, OR
#  - via default devices file: ./devices.txt (same dir as this script)
#
# devices.txt supports:
#  - one IP per line OR comma-separated IPs
#  - blank lines
#  - comments starting with '#'
#
# Examples:
#   ./run_all_tests.sh -d 192.168.1.50,192.168.1.51 -a
#   ./run_all_tests.sh -f ./devices.txt -a
#   ./run_all_tests.sh            # uses default ./devices.txt
# --------------------------------------------

DEVICES_CSV=""
DEVICE_FILE=""
PORTS="80,443"
WIFI_IFACE="wlan0"
PING_COUNT_WIFI=30
PING_COUNT_REACH=10
PING_TIMEOUT=1
TCP_TIMEOUT=2
DO_ARPING=0
LOG_DIR="./logs"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DEVICE_FILE="${SCRIPT_DIR}/devices.txt"

usage() {
  cat <<EOF
Usage: $0 [device options] [other options]

Device source (choose one):
  -d  Comma-separated device IPs, e.g. 192.168.1.50,192.168.1.51
  -f  Path to device IP file (default: ${DEFAULT_DEVICE_FILE})

If neither -d nor -f is given, the script tries to read:
  ${DEFAULT_DEVICE_FILE}

Other options:
  -p  Ports CSV for reachability test (default: 80,443)
  -w  Wi-Fi interface for snapshot (default: wlan0)
  -c  Ping count for Wi-Fi snapshot (default: 30)
  -C  Ping count for reachability test (default: 10)
  -W  Ping timeout seconds (default: 1)
  -t  TCP timeout seconds (default: 2)
  -a  Enable arping in reachability test (recommended for Wi-Fi sites)
  -h  Help

devices.txt format:
  - One IP per line OR comma-separated IPs on a line
  - Blank lines allowed
  - Comments allowed with '#'

Examples:
  $0 -d 192.168.1.50 -a
  $0 -d 192.168.1.50,192.168.1.51 -p 80,443 -a
  $0 -f ./devices.txt -a
  $0                 # uses default ${DEFAULT_DEVICE_FILE}
EOF
}

trim() { echo "$1" | xargs; }

load_devices_from_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "ERROR: Device file not found: $file" >&2
    exit 2
  fi

  local ips=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Remove comments
    line="${line%%#*}"
    line="$(trim "$line")"
    [[ -z "$line" ]] && continue

    # Support comma-separated or space-separated tokens
    line="${line//,/ }"
    for tok in $line; do
      tok="$(trim "$tok")"
      [[ -z "$tok" ]] && continue
      ips+=("$tok")
    done
  done < "$file"

  if [[ "${#ips[@]}" -eq 0 ]]; then
    echo "ERROR: No device IPs found in file: $file" >&2
    exit 2
  fi

  # De-duplicate while preserving order (simple approach)
  local uniq=()
  local seen=" "
  for ip in "${ips[@]}"; do
    if [[ "$seen" != *" $ip "* ]]; then
      uniq+=("$ip")
      seen+=" $ip "
    fi
  done

  # Export as CSV and array-friendly string
  (IFS=','; echo "${uniq[*]}")
}

while getopts ":d:f:p:w:c:C:W:t:ah" opt; do
  case "$opt" in
    d) DEVICES_CSV="$OPTARG" ;;
    f) DEVICE_FILE="$OPTARG" ;;
    p) PORTS="$OPTARG" ;;
    w) WIFI_IFACE="$OPTARG" ;;
    c) PING_COUNT_WIFI="$OPTARG" ;;
    C) PING_COUNT_REACH="$OPTARG" ;;
    W) PING_TIMEOUT="$OPTARG" ;;
    t) TCP_TIMEOUT="$OPTARG" ;;
    a) DO_ARPING=1 ;;
    h) usage; exit 0 ;;
    \?) echo "Unknown option: -$OPTARG" >&2; usage; exit 2 ;;
    :)  echo "Missing argument for -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

# Determine devices source
DEVICES_SOURCE=""

if [[ -n "$DEVICES_CSV" ]]; then
  DEVICES_SOURCE="CLI (-d)"
else
  if [[ -z "$DEVICE_FILE" ]]; then
    DEVICE_FILE="$DEFAULT_DEVICE_FILE"
    DEVICES_SOURCE="Default file (${DEVICE_FILE})"
  else
    DEVICES_SOURCE="File (-f ${DEVICE_FILE})"
  fi
  DEVICES_CSV="$(load_devices_from_file "$DEVICE_FILE")"
fi

mkdir -p "$LOG_DIR"
TS="$(date +"%Y%m%d_%H%M%S")"
RUN_LOG="${LOG_DIR}/run_all_${TS}.txt"
exec > >(tee -a "$RUN_LOG") 2>&1

echo "=== Run All Tests ==="
echo "Timestamp: $(date)"
echo "Run ID: ${TS}"
echo "Host: $(hostname)  User: $(whoami)"
echo "Devices source: ${DEVICES_SOURCE}"
echo "Devices: ${DEVICES_CSV}"
echo "Ports: ${PORTS}"
echo "Wi-Fi iface: ${WIFI_IFACE}"
echo "Wi-Fi ping count: ${PING_COUNT_WIFI}"
echo "Reachability ping count: ${PING_COUNT_REACH}"
echo "Ping timeout: ${PING_TIMEOUT}s"
echo "TCP timeout: ${TCP_TIMEOUT}s"
echo "ARPing enabled: $([[ "$DO_ARPING" -eq 1 ]] && echo YES || echo NO)"
echo

# Check scripts exist
WIFI_SCRIPT="${SCRIPT_DIR}/wifi_quality_snapshot.sh"
REACH_SCRIPT="${SCRIPT_DIR}/reachability_test.sh"
INET_SCRIPT="${SCRIPT_DIR}/internet_access_test.sh"

for f in "$WIFI_SCRIPT" "$REACH_SCRIPT" "$INET_SCRIPT"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: Missing script: $f" >&2
    exit 1
  fi
  if [[ ! -x "$f" ]]; then
    echo "NOTE: Script not executable: $f"
    echo "Fix: chmod +x \"$f\""
  fi
done

export RUN_TS="$TS"

echo "== 1) Wi-Fi quality snapshot =="
"$WIFI_SCRIPT" -I "$WIFI_IFACE" -c "$PING_COUNT_WIFI" -W "$PING_TIMEOUT" || true
echo

echo "== 2) Reachability tests (ping/ports/arp) per device =="
IFS=',' read -r -a DEV_ARR <<< "$DEVICES_CSV"
for ip in "${DEV_ARR[@]}"; do
  ip="$(trim "$ip")"
  [[ -z "$ip" ]] && continue
  echo "---- Device: $ip ----"
  if [[ "$DO_ARPING" -eq 1 ]]; then
    "$REACH_SCRIPT" -i "$ip" -p "$PORTS" -c "$PING_COUNT_REACH" -W "$PING_TIMEOUT" -t "$TCP_TIMEOUT" -a || true
  else
    "$REACH_SCRIPT" -i "$ip" -p "$PORTS" -c "$PING_COUNT_REACH" -W "$PING_TIMEOUT" -t "$TCP_TIMEOUT" || true
  fi
  echo
done

echo "== 3) Internet access constraints (DNS/HTTPS/MQTT) =="
"$INET_SCRIPT" || true
echo

echo "=== Completed. Master run log: ${RUN_LOG} ==="
echo "Individual logs are under: ${LOG_DIR}/"
echo
echo "TIP: To use default IPs, create/edit: ${DEFAULT_DEVICE_FILE}"
