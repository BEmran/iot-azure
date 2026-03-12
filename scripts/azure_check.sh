#!/bin/bash

# --- Configuration ---
LOG_POSTFIX=$(date +_%Y%m%d_%H%M%S)
LOG_FILE="iot_connectivity_check_results.txt${LOG_POSTFIX}.txt"
IOT_HUB_BASENAME="new-sense-iot"
IOT_HUB_HOSTNAME="https://$IOT_HUB_BASENAME.azureiotcentral.com/devices"
# ---------------------

# --- Execution ---

echo "Starting Azure IoT Connectivity Checks at $(date)" | tee -a "$LOG_FILE"
echo "Results being saved to: $LOG_FILE" | tee -a "$LOG_FILE"
echo "--------------------------------------------------" | tee -a "$LOG_FILE"


# Function to run a command, log a header, and append all output to the log file
run_test() {
    local test_name="$1"
    shift
    echo "" | tee -a "$LOG_FILE"
    echo "--- Running Test: $test_name ---" | tee -a "$LOG_FILE"
    # Execute the command and capture all output (stdout and stderr) to the log file
    if ! eval "$@"; then
        echo "Command failed: $*" | tee -a "$LOG_FILE"
    fi
    echo "--- End of Test: $test_name ---" | tee -a "$LOG_FILE"
}

# Clear previous log file content
> "$LOG_FILE"

# 1. curl -v https://azure.microsoft.com
run_test "General Outbound HTTPS Access (curl)" "curl -v https://azure.microsoft.com"


# 2. openssl s_client -connect <iot-hub>:8883 -servername <iot-hub>
# We use 'echo quit |' to gracefully close the connection after the TLS handshake finishes.
run_test "TLS/MQTT Connectivity (openssl)" "echo quit | openssl s_client -connect $IOT_HUB_HOSTNAME:8883 -servername $IOT_HUB_HOSTNAME"


# 3. telnet <iot-hub> 8883
# Use 'timeout' to prevent telnet from hanging indefinitely if the connection works but no data is sent.
run_test "Raw TCP Connectivity (telnet)" "timeout 10 telnet $IOT_HUB_HOSTNAME 8883"


echo "" | tee -a "$LOG_FILE"
echo "--------------------------------------------------" | tee -a "$LOG_FILE"
echo "Connectivity checks completed at $(date). Review '$LOG_FILE' for details." | tee -a "$LOG_FILE"

