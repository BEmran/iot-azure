#FFFFFF#FFFFFF#!/usr/bin/env python3
"""
pi_iothub.py
Simple Raspberry Pi device client for Azure IoT Hub:
- sends telemetry periodically
- listens for cloud-to-device (C2D) messages and prints them
"""

import time
import json
import uuid
import socket
import concurrent.futures
from azure.iot.device import IoTHubDeviceClient, Message

# ----------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------
DEVICE_CONNECTION_STRING = "HostName=NewSenceIoTHub.azure-devices.net;DeviceId=RPiIoT02;SharedAccessKey=sog0CXZkUGTUh8RMy7l1Pqg+BBk6V0tCqBaUm09Jm/Q="
DEVICE_ID = "myPi5Device"
TELEMETRY_INTERVAL_SEC = 10.0

# ----------------------------------------------------
# NETWORK CHECK
# ----------------------------------------------------

def is_network_connected(host_site="www.google.com", port=80, timeout=1.5):
    """
    Check internet connectivity by attempting to connect to a host.
    Default: Google DNS (8.8.8.8).
    Returns True if connection succeeds, False otherwise.
    """
    try:
        # DNS working?
        host = socket.gethostbyname(host_site)

        # TCP connectivity working?
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception as e:
        print("Failed to connect to network:", e)
        return False

def connect_to_network(max_retries=10, retry_interval=5):
    for attempt in range(1, max_retries + 1):
        print(f"Checking network connectivity (attempt {attempt})...")
        if is_network_connected():
            print("Network connected.")
            return True
        print(f"No network connection. Retrying in {retry_interval} seconds...")
        time.sleep(retry_interval)
    print(f"[FATAL] Could not connect to network {max_retries} retries.")
    return False
    
 # ===================

def send_with_timeout(client, message, timeout_sec=5):
    print("Sending:", message)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.send_message, message)
        try:
            future.result(timeout=timeout_sec)
            print("Message sent successfully.")
            return True

        except concurrent.futures.TimeoutError:
            print(f"[ERROR] send_message timed out after {timeout_sec} sec")
            return False

        except Exception as e:
            print("[ERROR] send_message failed:", e)
            return False
        
def create_iot_hub_client(conn_str):
    client = IoTHubDeviceClient.create_from_connection_string(conn_str)
    return client

def connect_to_iot_hub(client, max_retries=10, retry_interval=5):
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Connecting to Azure IoT Hub (attempt {attempt})...")
            client.connect()
            print("Successfully connected to IoT Hub.")
            # Set up C2D message handler
            client.on_message_received = handle_c2d_message
            return True

        except Exception as e:
            print(f"[ERROR] Azure connect failed: {e}")
            print(f"Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)

    print(f"[FATAL] Could not connect to Azure after {max_retries} retries.")
    return False

def handle_c2d_message(message):
    # message is an instance of azure.iot.device.Message
    print("Received C2D message:")
    try:
        body = message.data
        # If message is JSON, try to decode:
        try:
            parsed = json.loads(body.decode('utf-8'))
            print(json.dumps(parsed, indent=2))
        except Exception:
            print(body)
        # You can also read custom properties:
        for k, v in message.custom_properties.items():
            print(f"Property: {k} = {v}")
            if k == "command" and v == "reboot":
                print ("Reboot command received! (not really rebooting in this example)")
            elif k == "led" and v in ["on", "off"]:
                print(f"LED command received: turn {v} (not really changing LED in this example)")
            elif k == "firmwareVersion":
                print(f"Firmware version requested: {v} (not really updating firmware in this example)")
                
            else:
                print(f"Unknown command property: {k} = {v}")
    except Exception as e:
        print("Error processing message:", e)

def create_telemetry():
    telemetry = {
        "deviceId": DEVICE_ID,
        "temperature": round(20 + 10 * (0.5 - time.time() % 1), 2),  # mock temperature
        "humidity": round(50 + 20 * (0.5 - time.time() % 1), 2),     # mock humidity
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "messageId": str(uuid.uuid4())
    }
    return telemetry

def prepaere_message(telemetry):
    # azure-iot-device Message wrapper
    message = Message(json.dumps(telemetry))
    message.content_type = "application/json"
    message.content_encoding = "utf-8"
    # optional: add application properties
    message.custom_properties["sensorType"] = "mockSensor"
    return message

def send_telemetry(client, msg):
    try:
        print("Sending:", message)
        if not is_connected() or not client.connected:
            print("Client not connected, cannot send telemetry.")
            return False
        else:
            client.send_message(message)
            print("Telemetry sent successfully.")
            return True
    except Exception as e:
        print("Failed to send telemetry:", e)
        return False

def main():

    if not connect_to_network():
        return  # Fail early if completely unable
    
    client = create_iot_hub_client(DEVICE_CONNECTION_STRING)
    
    if not connect_to_iot_hub(client):
        return  # Fail early if completely unable

    print("System ready.")

    unsent_queue = []   # store unsent messages safely

    try:
        while True:
            msg = create_telemetry()
            message = prepaere_message(msg)
            
            # Attempt sending
            if not send_with_timeout(client, message):
                print("[WARN] Storing message for retry...")
                unsent_queue.append(message)

            # 4. If there are unsent messages, retry them
            retry_queue = []
            for old_msg in unsent_queue:
                if not send_with_timeout(client, old_msg):
                    retry_queue.append(old_msg)
            unsent_queue = retry_queue

            # 5. Check network health
            if not is_network_connected():
                print("[WARN] Network lost. Pausing telemetry.")
                if not connect_to_network():
                    print("[FATAL] Could not restore network. Exiting.")
                    break
                print("Network restored.")

            # 5. Check client health
            if not client.connected:
                print("[WARN] client connection lost. Pausing telemetry.")
                # Reconnect Azure IoT
                if not connect_iothub(client):
                    print("[FATAL] Could not reconnect to IoT Hub. Exiting.")
                    break
                print("Reconnected to IoT Hub.")
                
            time.sleep(TELEMETRY_INTERVAL_SEC)

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        client.disconnect()
        print("Disconnected.")
        print("Exiting.")
    
if __name__ == "__main__":
    main()