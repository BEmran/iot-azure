#!/bin/bash
# --- Configuration ---
LOG_POSTFIX=$(date +_%Y%m%d_%H%M%S)
LOG_FILE="ping_stability_results${LOG_POSTFIX}.txt"
# -------------------------------------
# Define IP addresses to ping 
GATEWAY = ""
IP = ""
AZURE = "azure.microsoft.com"
DEVICE = ""
IP_LIST=("$GATEWAY" "$IP" "$AZURE" "$DEVICE" "8.8.8.8")
# -------------------------------------
# Clear previous results and add a header
(
echo "======================================================"
echo "Ping Stability Test Log"
echo "Test initiated by user $USER on $(hostname)"
echo "Date/Time: $(date)"
echo "Log File: $LOG_FILE"
echo "======================================================"
echo ""

echo "Starting ping test at $(date)"
echo "--------------------------------"
echo "Timestamp: $(date)"

for ip in "${IP_LIST[@]}"; do
  echo "Pinging $ip..." | tee -a "$LOG_FILE"
  ping -c 5 "$ip"
  echo "--------------------------------"
done
echo ""

) > "$LOG_FILE" 2 > &1
echo "Ping test finished. Results stored in $LOG_FILE."