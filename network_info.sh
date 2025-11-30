#!/bin/bash
# --- Configuration ---
LOG_POSTFIX=$(date +_%Y%m%d_%H%M%S)
LOG_FILE="network_info_results${LOG_POSTFIX}.txt"

# Get the default network interface name (e.g., eth0, ens33, wlan0)
INTERFACE=$(ip route show default | awk '/default/ {print $5}')

if [ -z "$INTERFACE" ]; then
    echo "No default network interface found. Exiting."
    exit 1
fi

echo "Recording network information for interface: $INTERFACE"

# Get IP address
IP_ADDRESS=$(ip -4 addr show $INTERFACE | grep -oP 'inet \K[\d.]+')

# Get MAC address
MAC_ADDRESS=$(cat /sys/class/net/$INTERFACE/address)

# Get default gateway
GATEWAY=$(ip route show default | awk '/default/ {print $3}')

# Get DNS server(s) (reading from /etc/resolv.conf)
# This assumes standard Linux configuration where DNS servers are listed in resolv.conf
DNS_SERVERS=$(grep nameserver /etc/resolv.conf | awk '{print $2}' | tr '\n' ' ')

# Record the information in the text file
echo "--- Network Information Report ---" > $LOG_FILE
echo "Timestamp: $(date)" >> $LOG_FILE
echo "Interface: $INTERFACE" >> $LOG_FILE
echo "--------------------------------" >> $LOG_FILE
echo "IP Address:   $IP_ADDRESS" >> $LOG_FILE
echo "MAC Address:  $MAC_ADDRESS" >> $LOG_FILE
echo "Gateway:      $GATEWAY" >> $LOG_FILE
echo "DNS Servers:  $DNS_SERVERS" >> $LOG_FILE
echo "--------------------------------" >> $LOG_FILE
