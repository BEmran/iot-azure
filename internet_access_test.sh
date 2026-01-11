#!/usr/bin/env bash
set -euo pipefail

HTTPS_URLS=("https://www.microsoft.com" "https://azure.microsoft.com")
DNS_NAMES=("www.microsoft.com" "azure.microsoft.com" "global.azure-devices-provisioning.net")
TCP_443_HOST="www.microsoft.com"
MQTT_8883_HOST="test.mosquitto.org"
TIMEOUT_SEC=5
LOG_DIR="./logs"

while getopts ":m:t:h" opt; do
  case "$opt" in
    m) MQTT_8883_HOST="$OPTARG" ;;
    t) TIMEOUT_SEC="$OPTARG" ;;
    h)
      echo "Usage: $0 [-m <mqtt_8883_host>] [-t timeout_sec]"
      exit 0
      ;;
    \?) echo "Unknown option: -$OPTARG" >&2; exit 2 ;;
    :)  echo "Missing argument for -$OPTARG" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"
TS="$(date +"%Y%m%d_%H%M%S")"
OUT="${LOG_DIR}/internet_access_${TS}.txt"
exec > >(tee -a "$OUT") 2>&1

echo "=== Internet Access Constraints Test ==="
echo "Timestamp: $(date)"
echo "Host: $(hostname)  User: $(whoami)"
echo "Timeout: ${TIMEOUT_SEC}s"
echo "MQTT 8883 test host: ${MQTT_8883_HOST}"
echo

echo "== Default route & DNS =="
ip route | sed -n '1,5p' || true
echo "resolv.conf:"
cat /etc/resolv.conf || true
echo

echo "== DNS resolution =="
for name in "${DNS_NAMES[@]}"; do
  echo "-- nslookup ${name}"
  nslookup "$name" || true
  echo
done

echo "== HTTPS 443 checks (curl HEAD) =="
for url in "${HTTPS_URLS[@]}"; do
  echo "-- curl -I ${url}"
  curl -I --max-time "$TIMEOUT_SEC" "$url" || true
  echo
done

tcp_check() {
  local host="$1" port="$2"
  if command -v nc >/dev/null 2>&1; then
    nc -vz -w "$TIMEOUT_SEC" "$host" "$port"
  else
    if command -v timeout >/dev/null 2>&1; then
      timeout "${TIMEOUT_SEC}s" bash -c "cat < /dev/null > /dev/tcp/${host}/${port}" 2>/dev/null
    else
      bash -c "cat < /dev/null > /dev/tcp/${host}/${port}" 2>/dev/null
    fi
  fi
}

echo "== TCP connectivity checks =="
echo "-- TCP 443 to ${TCP_443_HOST}:443"
tcp_check "$TCP_443_HOST" 443 || echo "FAILED: TCP 443 to ${TCP_443_HOST}"
echo

echo "-- TCP 8883 to ${MQTT_8883_HOST}:8883"
tcp_check "$MQTT_8883_HOST" 8883 || echo "FAILED: TCP 8883 to ${MQTT_8883_HOST}"
echo

echo "=== Done. Log saved to: ${OUT} ==="
