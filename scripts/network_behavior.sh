#!/bin/bash

# --- Configuration ---
LOG_POSTFIX=$(date +_%Y%m%d_%H%M%S)
LOG_FILE="network_behavior_results${LOG_POSTFIX}.txt"

TARGET_HOST1="google.com"  # A common, reliable internet host to test connectivity against
TARGET_HOST2="azure.microsoft.com"  # Another reliable host
LIST_TARGET_HOSTS=("$TARGET_HOST1" "$TARGET_HOST2")

TARGET_PORT1="80"          # Common port for HTTP services
TARGET_PORT2="443"         # Common port for HTTPS services
LIST_TARGET_PORTS=("$TARGET_PORT1" "$TARGET_PORT2")

# ---------------------
# Clear previous results and add a header, redirecting all output of the group to the log file (including errors)
(
    echo "======================================================"
    echo "Network Behavior Test Log"
    echo "Test initiated by user $USER on $(hostname)"
    echo "Date/Time: $(date)"
    echo "Log File: $LOG_FILE"
    echo "======================================================"
    echo ""

    for TARGET_HOST in "${LIST_TARGET_HOSTS[@]}"; do
        for TARGET_PORT in "${LIST_TARGET_PORTS[@]}"; do
            echo "------------------------------------------------------"
            echo "the fllowing tests will be performed for each target host and port combination."
            echo "Target Host: $TARGET_HOST:$TARGET_PORT"

            # --- 1. Basic Connectivity Test: Ping ---
            echo "--- [1] Running Ping Command (5 packets) ---"
            echo "Command: ping -c 5 $TARGET_HOST"
            ping -c 5 "$TARGET_HOST"
            echo ""

            # --- 2. Route Tracing: Traceroute ---
            echo "--- [2] Running Traceroute Command ---"
            # Note: Using 'traceroute' command which is standard in Linux
            echo "Command: traceroute $TARGET_HOST"
            traceroute "$TARGET_HOST"
            echo ""

            # --- 3. Local Network Information: ARP Table ---
            echo "--- [3] Displaying ARP Table (Address Resolution Protocol) ---"
            # Using 'ip neigh' (modern Linux) or 'arp -a' (legacy net-tools)
            if command -v ip &> /dev/null; then
                echo "Command: ip neigh show"
                ip neigh show
            else
                echo "Command: arp -a"
                arp -a
            fi
            echo ""

            # --- 4. Port Connectivity Test: Telnet ---
            echo "--- [4] Running Telnet Test to Target Port ---"
            echo "Command: telnet $TARGET_HOST $TARGET_PORT"
            # Telnet often requires input handling tricks in scripts; using timeout for robustness.
            # The exit status indicates success or failure.
            timeout 5s telnet "$TARGET_HOST" "$TARGET_PORT" >/dev/null 2>&1
            if [ $? -eq 0 ]; then
                echo "Telnet successful: Port $TARGET_PORT is open and reachable."
            else
                echo "Telnet failed or timed out: Port $TARGET_PORT might be blocked or service is down."
            fi
            echo ""

            # --- 5. Application Layer Test: Curl ---
            echo "--- [5] Running Curl Command (Fetch HTTP headers) ---"
            echo "Command: curl -I https://$TARGET_HOST"
            curl -I "https://$TARGET_HOST"
            echo ""

            # --- 6. SSL/TLS Handshake Check: Openssl ---
            echo "--- [6] Running Openssl s_client Handshake Test ---"
            echo "Command: openssl s_client -connect $TARGET_HOST:$TARGET_PORT"
            # We use a non-interactive way to get basic handshake info and discard most output
            openssl s_client -connect "$TARGET_HOST":"$TARGET_PORT" -servername "$TARGET_HOST" </dev/null 2>/dev/null | sed -n '/^---/,/---$/p'
            # The sed command above filters the output to show just the certificate/handshake info block
            echo ""

            # --- 7. Bandwidth Performance Test: speedtest-cli ---
            echo "--- [7] Running Speedtest CLI (Requires speedtest-cli package) ---"
            echo "Command: speedtest-cli --simple"
            if command -v speedtest-cli &> /dev/null; then
                speedtest-cli --simple
            else
                echo "speedtest-cli is not installed or not found in PATH. Skipping."
            fi
            echo ""

            # --- 8. Additional Suggested Test: Netstat/SS (List Active Connections) ---
            echo "--- [8] Displaying Active Internet Connections using 'ss' ---"
            # 'ss' is the modern replacement for 'netstat'
            echo "Command: ss -tuln (TCP/UDP listening ports)"
            ss -tuln
            echo ""
            echo "Command: ss -antp (Active TCP connections with PIDs)"
            # Note: 'sudo' is often required to see PIDs (the -p flag) in the output.
            ss -antp || echo "Cannot display PIDs without root privileges. Try running the script with sudo for this section."

            echo "------------------------------------------------------"
            echo Network tests for $TARGET_HOST:$TARGET_PORT completed.
            echo "------------------------------------------------------"
        done
    done

    echo "======================================================"
    echo "Network Tests Complete."
    echo "======================================================"
    echo ""
) > "$LOG_FILE" 2 > &1

echo "All network test results have been saved to $LOG_FILE"