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
from azure.iot.device import ProvisioningDeviceClient, IoTHubDeviceClient, Message
import threading
import queue
import yaml
import logger # custom logger module

CONFIG_PATH = "config.yaml"
# Load configuration
CONFIG = None

# ----------------------------------------------------
# GLOBALS
# ----------------------------------------------------
send_queue = queue.Queue()
MSGTYPE = ["telemetry", "propertyUpdate"]

client = None
client_lock = threading.Lock()    
STOP_HEARTBEAT = False

START_TIME = 0.0
DEFAULT_TELEMETRY_INTERVAL_SEC = 10.0
DEFAULT_CHECK_INTERVAL = 5.0
DEFAULT_SEND_RETRY_INTERVAL = 5.0
DEFAULT_HEARTBEAT_INTERVAL_SEC = 60.0

CONNECTION_CONFIG = {"device_id": "", "device_connection_string": ""}
TELEMETRY_CONFIG = {"interval_sec": DEFAULT_TELEMETRY_INTERVAL_SEC, "heartbeat_interval_sec": DEFAULT_HEARTBEAT_INTERVAL_SEC}
NETWORK_CONFIG = {"check_interval_sec": DEFAULT_CHECK_INTERVAL, "send_retry_interval_sec": DEFAULT_SEND_RETRY_INTERVAL}
SYS_CONFIG = {"log_to_file": True, "print_level": "info", "log_level": "info", "log_dir": "logs", "log_file_max_size_bytes": 1_000_000}

# ----------------------------------------------------
# CONFIGURAION
# ----------------------------------------------------
def load_config(config_path=CONFIG_PATH):
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
            logger.trace("INFO", "Configuration loaded from {CONFIG_PATH}")
    except Exception as e:
        logger.trace("ERROR", f"Failed to load configuration: {e}")
        exit(1)
    return cfg

def parse_connection_config(config):
    if "connection" not in config:
        logger.trace("ERROR", "No connection configuration found.")
        exit(1)
    connection = config["connection"]
    
    if "method" not in config["connection"]:
        logger.trace("ERROR", "No connection method specified in configuration.")
        exit(1)
    method = config["connection"]["method"]
    
    if str(method).lower() == "dps":
        if "dps" not in config["connection"]:
            logger.trace("ERROR", "No DPS configuration found.")
            exit(1)
        dps = config["connection"]["dps"]
        if "device_id" not in dps or "symmetric_key" not in dps or "id_scope" not in dps:
            logger.trace("ERROR", "Incomplete DPS configuration.")
            exit(1)
        device_id = dps["device_id"]
        symmetric_key = dps["symmetric_key"]
        id_scope = dps["id_scope"]
        device_connection_string = create_connection_str_from_dps(device_id=device_id,
                                                                id_scope=id_scope,
                                                                symmetric_key=symmetric_key)
    else:
        if "hub" not in connection:
            logger.trace("ERROR", "No IoT Hub configuration found.")
            exit(1)
        hub = connection["hub"]
        device_connection_string = chub["device_connection_string"]
        if not device_connection_string:
            logger.trace("ERROR", "No device connection string found in configuration.")
            exit(1)
        device_id = device_connection_string.split("DeviceId=")[1].split(";")[0]
        if not device_id:
            logger.trace("ERROR", "Could not parse device ID from connection string.")
            exit(1)
    
    CONNECTION_CONFIG["device_id"] = device_id
    CONNECTION_CONFIG["device_connection_string"] = device_connection_string
    logger.trace("DEBUG", f"Connection configuration parsed {CONNECTION_CONFIG}")
    
def parse_telemetry_config(config):
    """Parse telemetry configuration"""
    global TELEMETRY_CONFIG, DEEFAULT_HEARTBEAT_INTERVAL_SEC, DEFAULT_TELEMETRY_INTERVAL_SEC
    if "app" not in config:
        logger.trace("WARN", f"No app configuration found, using default {TELEMETRY_CONFIG}")
        return
    app_config = config["app"]
    
    if "telemetry" not in app_config:
        logger.trace("WARN", f"No telemetry configuration found, using default {TELEMETRY_CONFIG}")
        return
    telemetry_config = app_config["telemetry"]
    
    interval_sec = telemetry_config.get("interval_sec", DEFAULT_TELEMETRY_INTERVAL_SEC)
    if interval_sec <= 0:
        logger.trace("WARN", f"Invalid telemetry interval {interval_sec}, using default {DEFAULT_TELEMETRY_INTERVAL_SEC}")
        interval_sec = DEFAULT_TELEMETRY_INTERVAL_SEC
    
    if "heartbeat_interval_sec" in telemetry_config:
        heartbeat_interval_sec = int(telemetry_config.get("heartbeat_interval_sec", DEFAULT_HEARTBEAT_INTERVAL_SEC))
        if heartbeat_interval_sec <= 0:
            logger.trace("WARN", f"Invalid heartbeat interval {heartbeat_interval_sec}, using default {DEFAULT_HEARTBEAT_INTERVAL_SEC}")
            heartbeat_interval_sec = DEFAULT_HEARTBEAT_INTERVAL_SEC
    
    TELEMETRY_CONFIG["interval_sec"] = interval_sec
    TELEMETRY_CONFIG["heartbeat_interval_sec"] = heartbeat_interval_sec
    logger.trace("DEBUG", f"Telemetry configuration parsed: {TELEMETRY_CONFIG}")
    
def parse_network_config(config):
    """Parse network configuration"""
    global NETWORK_CONFIG, DEFAULT_CHECK_INTERVAL, DEFAULT_SEND_RETRY_INTERVAL
    if "app" not in config:
        logger.trace("WARN", f"No app configuration found, using default {NETWORK_CONFIG}")
        return
    app_config = config["app"]
    
    if "network" not in app_config:
        logger.trace("WARN", f"No network configuration found, using default {NETWORK_CONFIG}")
        return
    network_config = app_config["network"]
    
    check_interval = network_config.get("check_interval_sec", DEFAULT_CHECK_INTERVAL)
    if check_interval <= 0:
        logger.trace("WARN", f"Invalid network check interval {check_interval}, using default {DEFAULT_CHECK_INTERVAL}")
        check_interval = DEFAULT_CHECK_INTERVAL
        
    send_retry_interval = network_config.get("send_retry_interval_sec", DEFAULT_SEND_RETRY_INTERVAL)
    if send_retry_interval <= 0:
        logger.trace("WARN", f"Invalid send retry interval {send_retry_interval}, using default {DEFAULT_SEND_RETRY_INTERVAL}")
        send_retry_interval = DEFAULT_SEND_RETRY_INTERVAL
    
    NETWORK_CONFIG["check_interval_sec"] = check_interval
    NETWORK_CONFIG["send_retry_interval_sec"] = send_retry_interval                     
    logger.trace("DEBUG", f"Network configuration parsed: {NETWORK_CONFIG}") 

def parse_system_config(config):
    """Parse system configuration"""
    if "sys" not in config:
        logger.trace("WARN", f"No sys configuration found, using default {SYS_CONFIG}")
        return
    sys_cfg = config["sys"]
    
    SYS_CONFIG["log_to_file"] = bool(sys_cfg.get("log_to_file", SYS_CONFIG["log_to_file"]))
    logger.trace("DEBUG", f"File logging enabled: {SYS_CONFIG['log_to_file']}")
    
    SYS_CONFIG["log_level"] = str(sys_cfg.get("log_level", SYS_CONFIG["log_level"])).upper()
    logger.trace("DEBUG", f"Log level set to: {SYS_CONFIG['log_level']}")
    
    SYS_CONFIG["print_level"] = str(sys_cfg.get("print_level", SYS_CONFIG["print_level"])).upper()
    logger.trace("DEBUG", f"Print level set to: {SYS_CONFIG['print_level']}")
    
    SYS_CONFIG["log_dir"] = str(sys_cfg.get("log_dir", SYS_CONFIG["log_dir"]))
    logger.trace("DEBUG", f"Log directory set to: {SYS_CONFIG['log_dir']}")
        
    SYS_CONFIG["log_file_max_size_bytes"] = int(sys_cfg.get("log_file_max_size_bytes", SYS_CONFIG["log_file_max_size_bytes"]))
    logger.trace("DEBUG", f"Log file max size set to: {SYS_CONFIG['log_file_max_size_bytes']}")
    
    logger.trace("DEBUG", f"System configuration parsed: {SYS_CONFIG}")

def apply_system_config():
    """Apply system configuration"""
    logger.set_file_logging_enabled(SYS_CONFIG["log_to_file"])
    logger.set_log_level(SYS_CONFIG["log_level"])
    logger.set_print_level(SYS_CONFIG["print_level"])
    logger.set_logs_dir(SYS_CONFIG["log_dir"])
    logger.set_max_file_size(SYS_CONFIG["log_file_max_size_bytes"])
    
                                                                  
# ----------------------------------------------------
# NETWORK CHECK
# ----------------------------------------------------

def is_network_connected(host_site="www.google.com", port=80, timeout=NETWORK_CONFIG["check_interval_sec"]):
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
        logger.trace("ERROR", f"Failed to connect to network: {e}")
        return False
    
# ----------------------------------------------------
# IOT HUB
# ----------------------------------------------------
def send_with_timeout(client, message, timeout_sec=NETWORK_CONFIG["send_retry_interval_sec"]):
    if message is None:
        logger.trace("ERROR", "No message to send.")
        return True  # nothing to send
    logger.trace("DEBUG", f"Sending: {message}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        if message[0] == MSGTYPE[0]:  # telemetry
            future = executor.submit(client.send_message, message[1])
        elif message[0] == MSGTYPE[1]:  # propertyUpdate
            properties_payload = {"IP": "192.168.0.1"}
            future = executor.submit(client.patch_twin_reported_properties, message[1])
        
        try:
            future.result(timeout=timeout_sec)
            logger.trace("INFO", "Message sent successfully.")
            return True

        except concurrent.futures.TimeoutError as exc:
            logger.trace("ERROR", f"send_message timed out: {exc} after {timeout_sec} sec")
            return False

        except Exception as e:
            logger.trace("ERROR", f"send_message failed: {e}")
            return False
        
# =========================================================
def create_connection_str_from_dps(device_id, id_scope, symmetric_key):
    if not device_id or not id_scope or not symmetric_key:
        logger.trace("ERROR", "Could not parse device ID from connection string.")
        exit(1)

    logger.trace("INFO", "Registering device with DPS...")

    # 1) Connect to DPS
    provisioning_client = ProvisioningDeviceClient.create_from_symmetric_key(
        provisioning_host="global.azure-devices-provisioning.net",
        registration_id=device_id,
        id_scope=id_scope,
        symmetric_key=symmetric_key
    )

    # 2) Register and get assigned IoT Hub
    registration_result = provisioning_client.register()

    if registration_result.status != "assigned":
        raise Runtimelogger.trace("ERROR", 
            f"DPS registration failed: {registration_result.status}"
        )

    hub_hostname = registration_result.registration_state.assigned_hub
    logger.trace("DEBUG", f"DPS assigned hub: {hub_hostname}")

    # 3) Generate device connection string
    device_conn_str = (
        f"HostName={hub_hostname};"
        f"DeviceId={device_id};"
        f"SharedAccessKey={symmetric_key}"
    )

    logger.trace("DEBUG", f"Generated device connection string: {device_conn_str}")
    return device_conn_str
        
def create_iot_hub_client(conn_str):
    logger.trace("INFO", "Creating new IoTHubDeviceClient...")
    client = IoTHubDeviceClient.create_from_connection_string(conn_str)
    return client

def connect_to_iot_hub(client):
    with client_lock:
        if not client.connected:
            try:
                logger.trace("INFO", "Connecting to Azure IoT Hub...")
                client.connect()
                logger.trace("INFO", "Successfully connected to IoT Hub.")

            except Exception as e:
                logger.trace("ERROR", f"Azure connect failed: {e}")
                time.sleep(retry_interval)
        
    # Set up C2D message handler
    client.on_message_received = handle_c2d_message
    client.on_method_request_received = command_handler
    return True

def handle_c2d_message(message):
    # message is an instance of azure.iot.device.Message
    logger.trace("INFO", "Received C2D message")
    try:
        body = message.data
        # If message is JSON, try to decode:
        try:
            parsed = json.loads(body.decode('utf-8'))
            logger.trace("DEBUG", f"message: {json.dumps(parsed, indent=2)}")
        except Exception:
            logger.trace("ERROR", f"failed parsing message as JSON: {e}")
        
        # You can also read custom properties:
        for k, v in message.custom_properties.items():
            logger.trace("INFO", f"Property: {k} = {v}")
            if k == "command" and v == "reboot":
                logger.trace("INFO", "Reboot command received! (not really rebooting in this example)")
            elif k == "led" and v in ["on", "off"]:
                logger.trace("INFO", f"LED command received: turn {v} (not really changing LED in this example)")
            elif k == "firmwareVersion":
                logger.trace("INFO", f"Firmware version requested: {v} (not really updating firmware in this example)")
                
            else:
                logger.trace("WARN", f"Unknown command property: {k} = {v}")
    
    except Exception as e:
        logger.trace("ERROR", f"failed processing message: {e}")

# Define your callback function
# This function must accept a 'method_request' argument
async def command_handler(RebootMaster):
    """
    Handler for incoming direct methods (commands).
    """
    logger.trace("INFO", f"\nCommand received: {method_request.name}")
    logger.trace("DEBUG", f"Payload: {method_request.payload}")

    # Process the command based on its name
    if method_request.name == "rebootMaster":
        # Simulate the action
        logger.trace("DEBUG", "Initiating device reboot...")

        # Create a response
        response_payload = {"status": "Reboot initiated", "timestamp": "..."}
        status = 200 # HTTP status code for success
        response = MethodResponse.create_from_method_request(
            method_request, status, response_payload
        )
    
    else:
        # Handle unknown commands
        status = 404
        response_payload = {"error": "Command not found"}
        response = MethodResponse.create_from_method_request(
            method_request, status, response_payload
        )
    await client.send_method_response(response)
    # Send the response back to the cloud
    print("Response sent.")

# def prepaere_message(telemetry):
#     # azure-iot-device Message wrapper
#     message = Message(json.dumps(telemetry))
#     # message.content_type = "application/json"
#     message.content_encoding = "utf-8"
#     return message

# ----------------------------------------------------
# creating messages
# ----------------------------------------------------
def create_heartbeat():
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    msg = Message(json.dumps(payload))
    msg.custom_properties["$.sub"] = "Heartbeat"  # Component name
    return msg

def create_telemetry():
    payload = {
        "Temperature": round(20 + 10 * (0.5 - time.time() % 1), 2),  # mock temperature
        "Humidity": round(50 + 20 * (0.5 - time.time() % 1), 2),     # mock humidity
    }
    msg = Message(json.dumps(payload))
    return msg

def create_master_info_msg():
    global START_TIME
    # PnP convention requires wrapping component properties in a dictionary 
    # with specific metadata fields: __t ("timestamp" or "type")
    payload = {
        "CONN": "GSM",
        "MasterInfo": {
            "__t": "c",  # indicates component
            "ID": int(111),
            "IP": str(socket.gethostbyname(socket.gethostname())),
            "Name": "iot-device-001",
        }
    }
    return payload

# ----------------------------------------------------
# SENDER TASK THREAD
# ----------------------------------------------------
def sender_task(client, running_event):
    while running_event.is_set():
        msg = send_queue.get()  # blocking wait for next message

        # Wait until internet is available
        while not is_network_connected():
            logger.trace("WARN", f"No internet. Retrying in {NETWORK_CONFIG["check_interval_sec"]} sec...")
            time.sleep(NETWORK_CONFIG["check_interval_sec"])

        # Ensure Azure client is connected
        if not connect_to_iot_hub(client):
            logger.trace("WARN", "Will retry sending message later...")
            time.sleep(NETWORK_CONFIG["check_interval_sec"])
            send_queue.put(msg)  # Put back into queue
            continue

        # Try sending the message
        try:
            send_with_timeout(client, msg)
            
        except Exception as e:
            logger.trace("ERROR", f"send_message failed: {e}")
            logger.trace("WARN", "Retrying later...")
            send_queue.put(msg)
            time.sleep(NETWORK_CONFIG["send_retry_interval_sec"])

        time.sleep(0.1)  # prevent CPU spin
    
    logger.trace("INFO", "Sender worker thread exiting...")

# ----------------------------------------------------
# SENSOR TASK THREAD – RUNS AT ITS OWN SPEED
# ----------------------------------------------------
def sensor_task(running_event):
    last_time = 0
    while running_event.is_set():
        now = time.time()
        if now - last_time >= TELEMETRY_CONFIG["interval_sec"]:
            last_time = now
            payload = create_telemetry()
            # payload = prepaere_message(message)
            send_queue.put([MSGTYPE[0], payload])
            logger.trace("DEBUG", "Queuing message: {payload}")
        time.sleep(0.1)

# ----------------------------------------------------
# HEARTBEAT TASK THREAD – DIFFERENT RATE
# ----------------------------------------------------
def heartbeat_task(running_event):
    last_time = 0
    while running_event.is_set():
        now = time.time()
        if not STOP_HEARTBEAT:
            if now - last_time >= TELEMETRY_CONFIG["heartbeat_interval_sec"]:
                last_time = now
                message = create_heartbeat()
                # payload = prepaere_message(message)
                send_queue.put([MSGTYPE[0], message])
                logger.trace("DEBUG", "Queuing message: {message}")
        time.sleep(0.1)

# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    global START_TIME
    START_TIME = time.time()
    logger.trace("DEBUG", "Starting Azure IoT device client at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(START_TIME))}")
    
    # parse configuration
    config = load_config()
    parse_connection_config(config)
    parse_telemetry_config(config)
    parse_network_config(config)
    parse_system_config(config)
    apply_system_config()

    if not is_network_connected():
        logger.trace("ERROR", "Could not connect to network.")
        return  # Fail early if completely unable
    
    client = create_iot_hub_client(conn_str=CONNECTION_CONFIG["device_connection_string"])
    
    if not connect_to_iot_hub(client):
        logger.trace("ERROR", "Could not connect to IoT Hub.")
        return  # Fail early if completely unable

    logger.trace("INFO", "System ready.")
    
    # Start background sender thread
    running = threading.Event()
    running.set()
    # create threads
    sender_worker = threading.Thread(target=sender_task, args=(client, running), daemon=True)
    sensor_worker = threading.Thread(target=sensor_task, args=(running,), daemon=True)
    heartbeat_worker = threading.Thread(target=heartbeat_task, args=(running,), daemon=True)
    # start threads
    sender_worker.start()
    sensor_worker.start()
    heartbeat_worker.start()
    
    unsent_queue = []   # store unsent messages safely

    try:
        # Send initial MasterInfo property update
        msg = create_master_info_msg()
        logger.trace("DEBUG", "Queuing message: {message}")
        send_queue.put([MSGTYPE[1], msg])
            
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.trace("WARN", "User canceled the program...")
        
    finally:
        running.clear()
        logger.close_logger()
        # sender_worker.join(timeout=2)
        # sensor_worker.join(timeout=1)
        # heartbeat_worker.join(timeout=1)
        time.sleep(2)  # wait for sender thread to exit
        client.disconnect()
        logger.trace("INFO", "Disconnected.")
        logger.trace("INFO", "Exiting.")
        
if __name__ == "__main__":
    main()