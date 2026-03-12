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
from azure.iot.device import ProvisioningDeviceClient, IoTHubDeviceClient, MethodResponse, Message
import threading
import queue
import yaml
import logger # custom logger module
from slave import Slave # custom slave module

CONFIG_PATH = "config.yaml"
# Load configuration
CONFIG = None

# ----------------------------------------------------
# GLOBALS
# ----------------------------------------------------
send_queue = queue.Queue()
command_queue = queue.Queue()
MSGTYPE = ["telemetry", "propertyUpdate"]

client = None
client_lock = threading.Lock()    
STOP_HEARTBEAT = False

SLAVE_READY_STATE = False
ERROR_STATE = False

START_TIME = 0.0
DEFAULT_TELEMETRY_INTERVAL_SEC = 10.0
DEFAULT_CHECK_INTERVAL = 5.0
DEFAULT_SEND_RETRY_INTERVAL = 5.0
DEFAULT_HEARTBEAT_INTERVAL_SEC = 60.0
DEFAULT_SLAVE_CONFIG = {"num": 0, "relay_gpio_line": 17, "power_off_delay_sec": 5.0}

CONNECTION_CONFIG = {"device_id": "", "device_connection_string": ""}
TELEMETRY_CONFIG = {"interval_sec": DEFAULT_TELEMETRY_INTERVAL_SEC, "heartbeat_interval_sec": DEFAULT_HEARTBEAT_INTERVAL_SEC}
NETWORK_CONFIG = {"check_interval_sec": DEFAULT_CHECK_INTERVAL, "send_retry_interval_sec": DEFAULT_SEND_RETRY_INTERVAL}
SYS_CONFIG = {"log_to_file": True, "print_level": "info", "log_level": "info", "log_dir": "logs", "log_file_max_size_bytes": 1_000_000}
HARDWARE_CONFIG = {"slave": DEFAULT_SLAVE_CONFIG}

# ----------------------------------------------------
# change status
# ----------------------------------------------------  
def status():
    global SLAVE_READY_STATE, ERROR_STATE
    if ERROR_STATE:
        return "Error"
    elif not SLAVE_READY_STATE:
        return "AwaitingSlave"
    else:
        return "Ready"
# ----------------------------------------------------
# CONFIGURAION
# ----------------------------------------------------
def load_config(config_path=CONFIG_PATH):
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
            logger.info("Configuration loaded from {CONFIG_PATH}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        exit(1)
    return cfg

def parse_connection_config(config):
    if "connection" not in config:
        logger.error("No connection configuration found.")
        exit(1)
    connection = config["connection"]
    
    if "method" not in config["connection"]:
        logger.error("No connection method specified in configuration.")
        exit(1)
    method = config["connection"]["method"]
    
    if str(method).lower() == "dps":
        if "dps" not in config["connection"]:
            logger.error("No DPS configuration found.")
            exit(1)
        dps = config["connection"]["dps"]
        if "device_id" not in dps or "symmetric_key" not in dps or "id_scope" not in dps:
            logger.error("Incomplete DPS configuration.")
            exit(1)
        device_id = dps["device_id"]
        symmetric_key = dps["symmetric_key"]
        id_scope = dps["id_scope"]
        device_connection_string = create_connection_str_from_dps(device_id=device_id,
                                                                id_scope=id_scope,
                                                                symmetric_key=symmetric_key)
    else:
        if "hub" not in connection:
            logger.error("No IoT Hub configuration found.")
            exit(1)
        hub = connection["hub"]
        device_connection_string = chub["device_connection_string"]
        if not device_connection_string:
            logger.error("No device connection string found in configuration.")
            exit(1)
        device_id = device_connection_string.split("DeviceId=")[1].split(";")[0]
        if not device_id:
            logger.error("Could not parse device ID from connection string.")
            exit(1)
    
    CONNECTION_CONFIG["device_id"] = device_id
    CONNECTION_CONFIG["device_connection_string"] = device_connection_string
    logger.debug(f"Connection configuration parsed {CONNECTION_CONFIG}")
    
def parse_telemetry_config(config):
    """Parse telemetry configuration"""
    global TELEMETRY_CONFIG, DEEFAULT_HEARTBEAT_INTERVAL_SEC, DEFAULT_TELEMETRY_INTERVAL_SEC
    if "app" not in config:
        logger.warn(f"No app configuration found, using default {TELEMETRY_CONFIG}")
        return
    app_config = config["app"]
    
    if "telemetry" not in app_config:
        logger.warn(f"No telemetry configuration found, using default {TELEMETRY_CONFIG}")
        return
    telemetry_config = app_config["telemetry"]
    
    interval_sec = telemetry_config.get("interval_sec", DEFAULT_TELEMETRY_INTERVAL_SEC)
    if interval_sec <= 0:
        logger.warn(f"Invalid telemetry interval {interval_sec}, using default {DEFAULT_TELEMETRY_INTERVAL_SEC}")
        interval_sec = DEFAULT_TELEMETRY_INTERVAL_SEC
    
    if "heartbeat_interval_sec" in telemetry_config:
        heartbeat_interval_sec = int(telemetry_config.get("heartbeat_interval_sec", DEFAULT_HEARTBEAT_INTERVAL_SEC))
        if heartbeat_interval_sec <= 0:
            logger.warn(f"Invalid heartbeat interval {heartbeat_interval_sec}, using default {DEFAULT_HEARTBEAT_INTERVAL_SEC}")
            heartbeat_interval_sec = DEFAULT_HEARTBEAT_INTERVAL_SEC
    
    TELEMETRY_CONFIG["interval_sec"] = interval_sec
    TELEMETRY_CONFIG["heartbeat_interval_sec"] = heartbeat_interval_sec
    logger.debug(f"Telemetry configuration parsed: {TELEMETRY_CONFIG}")
    
def parse_network_config(config):
    """Parse network configuration"""
    global NETWORK_CONFIG, DEFAULT_CHECK_INTERVAL, DEFAULT_SEND_RETRY_INTERVAL
    if "app" not in config:
        logger.warn(f"No app configuration found, using default {NETWORK_CONFIG}")
        return
    app_config = config["app"]
    
    if "network" not in app_config:
        logger.warn(f"No network configuration found, using default {NETWORK_CONFIG}")
        return
    network_config = app_config["network"]
    
    check_interval = network_config.get("check_interval_sec", DEFAULT_CHECK_INTERVAL)
    if check_interval <= 0:
        logger.warn(f"Invalid network check interval {check_interval}, using default {DEFAULT_CHECK_INTERVAL}")
        check_interval = DEFAULT_CHECK_INTERVAL
        
    send_retry_interval = network_config.get("send_retry_interval_sec", DEFAULT_SEND_RETRY_INTERVAL)
    if send_retry_interval <= 0:
        logger.warn(f"Invalid send retry interval {send_retry_interval}, using default {DEFAULT_SEND_RETRY_INTERVAL}")
        send_retry_interval = DEFAULT_SEND_RETRY_INTERVAL
    
    NETWORK_CONFIG["check_interval_sec"] = check_interval
    NETWORK_CONFIG["send_retry_interval_sec"] = send_retry_interval                     
    logger.debug(f"Network configuration parsed: {NETWORK_CONFIG}") 

def parse_system_config(config):
    """Parse system configuration"""
    if "sys" not in config:
        logger.warn(f"No sys configuration found, using default {SYS_CONFIG}")
        return
    sys_cfg = config["sys"]
    
    SYS_CONFIG["log_to_file"] = bool(sys_cfg.get("log_to_file", SYS_CONFIG["log_to_file"]))
    logger.debug(f"File logging enabled: {SYS_CONFIG['log_to_file']}")
    
    SYS_CONFIG["log_level"] = str(sys_cfg.get("log_level", SYS_CONFIG["log_level"])).upper()
    logger.debug(f"Log level set to: {SYS_CONFIG['log_level']}")
    
    SYS_CONFIG["print_level"] = str(sys_cfg.get("print_level", SYS_CONFIG["print_level"])).upper()
    logger.debug(f"Print level set to: {SYS_CONFIG['print_level']}")
    
    SYS_CONFIG["log_dir"] = str(sys_cfg.get("log_dir", SYS_CONFIG["log_dir"]))
    logger.debug(f"Log directory set to: {SYS_CONFIG['log_dir']}")
        
    SYS_CONFIG["log_file_max_size_bytes"] = int(sys_cfg.get("log_file_max_size_bytes", SYS_CONFIG["log_file_max_size_bytes"]))
    logger.debug(f"Log file max size set to: {SYS_CONFIG['log_file_max_size_bytes']}")
    
    logger.debug(f"System configuration parsed: {SYS_CONFIG}")

def parse_hardware_config(config):
    """Parse hardware configuration"""
    global HARDWARE_CONFIG, SLAVE_CONFIG
    if "hardware" not in config:
        logger.warn(f"No hardware configuration found, using default {HARDWARE_CONFIG}")
        return
    hw_cfg = config["hardware"]
    
    if "slave" not in hw_cfg:
        logger.warn(f"No slave configuration found, using default {HARDWARE_CONFIG}")
        return
    
    HARDWARE_CONFIG["slave"] = parse_slave_config(hw_cfg["slave"])
    logger.debug(f"Hardware configuration parsed: {HARDWARE_CONFIG}")

def parse_slave_config(slave_cfg = DEFAULT_SLAVE_CONFIG):
    """Get slave configuration"""
    num = slave_cfg.get("num", DEFAULT_SLAVE_CONFIG["num"])
    if num < 0:
        logger.warn(f"Invalid slave num {num}, using default {DEFAULT_SLAVE_CONFIG['num']}")
        num = DEFAULT_SLAVE_CONFIG["num"]
    
    power_off_delay_sec = float(slave_cfg.get("power_off_delay_sec", DEFAULT_SLAVE_CONFIG["power_off_delay_sec"]))
    if power_off_delay_sec < 0:
        logger.warn(f"Invalid power on delay {power_off_delay_sec}, using default {DEFAULT_SLAVE_CONFIG['power_off_delay_sec']}")
        power_off_delay_sec = DEFAULT_SLAVE_CONFIG["power_off_delay_sec"]

    relay_gpio_line = int(slave_cfg.get("relay_gpio_line", DEFAULT_SLAVE_CONFIG["relay_gpio_line"]))
    if relay_gpio_line < 0:
        logger.warn(f"Invalid relay GPIO line {relay_gpio_line}, using default {DEFAULT_SLAVE_CONFIG['relay_gpio_line']}")
        relay_gpio_line = DEFAULT_SLAVE_CONFIG["relay_gpio_line"]
    
    result_config = {"num": num, "relay_gpio_line": relay_gpio_line, "power_off_delay_sec": power_off_delay_sec}
    logger.debug(f"Slave configuration parsed: {result_config}")
    return result_config

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
        logger.error(f"Failed to connect to network: {e}")
        return False
    
# ----------------------------------------------------
# IOT HUB
# ----------------------------------------------------
def send_with_timeout(client, message, timeout_sec=NETWORK_CONFIG["send_retry_interval_sec"]):
    if message is None:
        logger.error("No message to send.")
        return True  # nothing to send
    logger.debug(f"Sending: {message}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        if message[0] == MSGTYPE[0]:  # telemetry
            future = executor.submit(client.send_message, message[1])
        elif message[0] == MSGTYPE[1]:  # propertyUpdate
            properties_payload = {"IP": "192.168.0.1"}
            future = executor.submit(client.patch_twin_reported_properties, message[1])
        
        try:
            future.result(timeout=timeout_sec)
            logger.info("Message sent successfully.")
            return True

        except concurrent.futures.TimeoutError as exc:
            logger.error(f"send_message timed out: {exc} after {timeout_sec} sec")
            return False

        except Exception as e:
            logger.error(f"send_message failed: {e}")
            return False
        
# =========================================================
def create_connection_str_from_dps(device_id, id_scope, symmetric_key):
    if not device_id or not id_scope or not symmetric_key:
        logger.error("Could not parse device ID from connection string.")
        exit(1)

    logger.info("Registering device with DPS...")

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
        raise Runtimelogger.error(
            f"DPS registration failed: {registration_result.status}"
        )

    hub_hostname = registration_result.registration_state.assigned_hub
    logger.debug(f"DPS assigned hub: {hub_hostname}")

    # 3) Generate device connection string
    device_conn_str = (
        f"HostName={hub_hostname};"
        f"DeviceId={device_id};"
        f"SharedAccessKey={symmetric_key}"
    )

    logger.debug(f"Generated device connection string: {device_conn_str}")
    return device_conn_str
        
def create_iot_hub_client(conn_str):
    logger.info("Creating new IoTHubDeviceClient...")
    client = IoTHubDeviceClient.create_from_connection_string(conn_str)
    return client

def connect_to_iot_hub(client):
    with client_lock:
        if not client.connected:
            try:
                logger.info("Connecting to Azure IoT Hub...")
                client.connect()
                logger.info("Successfully connected to IoT Hub.")

            except Exception as e:
                logger.error(f"Azure connect failed: {e}")
                time.sleep(retry_interval)
        
    # Set up C2D message handler
    client.on_message_received = handle_c2d_message
    client.on_method_request_received = command_handler
    return True

def handle_c2d_message(message):
    # message is an instance of azure.iot.device.Message
    logger.info("Received C2D message")
    try:
        body = message.data
        # If message is JSON, try to decode:
        try:
            parsed = json.loads(body.decode('utf-8'))
            logger.debug(f"message: {json.dumps(parsed, indent=2)}")
        except Exception:
            logger.error(f"failed parsing message as JSON: {e}")
        
        # You can also read custom properties:
        for k, v in message.custom_properties.items():
            logger.info(f"Property: {k} = {v}")
            if k == "command" and v == "reboot":
                logger.info("Reboot command received! (not really rebooting in this example)")
            elif k == "led" and v in ["on", "off"]:
                logger.info(f"LED command received: turn {v} (not really changing LED in this example)")
            elif k == "firmwareVersion":
                logger.info(f"Firmware version requested: {v} (not really updating firmware in this example)")
                
            else:
                logger.warn(f"Unknown command property: {k} = {v}")
    
    except Exception as e:
        logger.error(f"failed processing message: {e}")

def command_handler(method_request):
    """
    Handler for incoming direct methods (commands).
    """
    logger.info(f"Received command: {method_request.name}")
    logger.debug(f"Received command {method_request.name} with payload {method_request.payload}")
    # Push the request to the queue
    command_queue.put(method_request)

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
        "status": status(),
    }

    msg = Message(json.dumps(payload))
    # msg.custom_properties["$.sub"] = "Heartbeat"  # Component name
    return msg

def create_telemetry():
    payload = {
        "temperature": round(20 + 10 * (0.5 - time.time() % 1), 2),  # mock temperature
        "humidity": round(50 + 20 * (0.5 - time.time() % 1), 2),     # mock humidity
    }
    msg = Message(json.dumps(payload))
    return msg

def create_master_info_msg():
    # global START_TIME
    # PnP convention requires wrapping component properties in a dictionary 
    # with specific metadata fields: __t ("timestamp" or "type")
    # payload = {
    #     "MasterInfo": {
    #         "__t": "c",  # indicates component
    #         "id": int(111),
    #         "ip": str(socket.gethostbyname(socket.gethostname())),
    #         "name": "iot-device-001",
    #     }
    # }
    payload = {
        "id": int(111),
        "ip": str(socket.gethostbyname(socket.gethostname())),
        "name": "iot-device-001",
    }
    return payload

# ======================================================
# COMMAND PROCESSOR THREAD
# ======================================================
def restart_slave_task(delay_sec):
    global SLAVE_READY_STATE
    if delay_sec is None or delay_sec < 0:
        delay_sec = 0
    logger.debug(f"Restarting slave will start in {delay_sec} seconds...")
    SLAVE_READY_STATE = False
    time.sleep(delay_sec)
    
    Slave(
        relay_gpio_line=HARDWARE_CONFIG["slave"]["relay_gpio_line"],
        num=HARDWARE_CONFIG["slave"]["num"],
        debug=False
    ).power_cycle(off_duration=HARDWARE_CONFIG["slave"]["power_off_delay_sec"])
    
    SLAVE_READY_STATE = True
    logger.debug("Slave restarted and ready.")
    
def restart_cmd(cmd_payload):
    logger.info("Restart command received.")
    delay = cmd_payload.get("delay", 0)
    reason = cmd_payload.get("reason", "unspecified")
    logger.debug(f"Restarting in {delay} seconds. Reason: {reason}")
    threading.Thread(target=restart_slave_task, args=(delay, )).start()
    return "restarted", 200

def command_processor_task(client, running_event):

    logger.info("Command processor ready...")

    while running_event.is_set():
        cmd_request = command_queue.get()  # waits automatically

        cmd_name = cmd_request.name
        payload = cmd_request.payload
        logger.debug(f"processing command {cmd_name} and payload {payload}")

        try:
            # COMMAND ROUTING
            
            if cmd_name == "restart":
                status, code = restart_cmd(payload)

            # elif cmd_name == "getStatus":
            #     response_payload = {
            #         "status": "running",
            #         "cpuTemp": 46.3,
            #         "code": 200
            #     }
            #     status_code = 200

            else:
                logger.warn(f"Unknown command {cmd_name}")
                status, code = "Unknown command", 404

        except Exception as e:
            logger.error(f"Processing error: {e}")
            status, code = "error", 500

        # SEND COMMAND RESPONSE
        response_payload = {"status": status, "code": code}
        response = MethodResponse.create_from_method_request(
            cmd_request,
            code,
            response_payload
        )
        client.send_method_response(response)

        logger.info(f"[CMD] Completed command {cmd_name}")

# ----------------------------------------------------
# SENDER TASK THREAD
# ----------------------------------------------------
def sender_task(client, running_event):
    while running_event.is_set():
        msg = send_queue.get()  # blocking wait for next message

        # Wait until internet is available
        while not is_network_connected():
            logger.warn(f"No internet. Retrying in {NETWORK_CONFIG["check_interval_sec"]} sec...")
            time.sleep(NETWORK_CONFIG["check_interval_sec"])

        # Ensure Azure client is connected
        if not connect_to_iot_hub(client):
            logger.warn("Will retry sending message later...")
            time.sleep(NETWORK_CONFIG["check_interval_sec"])
            send_queue.put(msg)  # Put back into queue
            continue

        # Try sending the message
        try:
            send_with_timeout(client, msg)
            
        except Exception as e:
            logger.error(f"send_message failed: {e}")
            logger.warn("Retrying later...")
            send_queue.put(msg)
            time.sleep(NETWORK_CONFIG["send_retry_interval_sec"])

        time.sleep(0.1)  # prevent CPU spin
    
    logger.info("Sender worker thread exiting...")

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
            logger.debug("Queuing message: {payload}")
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
                logger.debug("Queuing message: {message}")
        time.sleep(0.1)

# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    global START_TIME
    START_TIME = time.time()
    logger.debug("Starting Azure IoT device client at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(START_TIME))}")
    
    # parse configuration
    config = load_config()
    parse_connection_config(config)
    parse_telemetry_config(config)
    parse_network_config(config)
    parse_system_config(config)
    parse_hardware_config(config)
    apply_system_config()

    if not is_network_connected():
        logger.error("Could not connect to network.")
        return  # Fail early if completely unable
    
    client = create_iot_hub_client(conn_str=CONNECTION_CONFIG["device_connection_string"])
    
    if not connect_to_iot_hub(client):
        logger.error("Could not connect to IoT Hub.")
        return  # Fail early if completely unable

    logger.info("System ready.")
    
    # Start background sender thread
    running = threading.Event()
    running.set()
    # create threads
    sender_worker = threading.Thread(target=sender_task, args=(client, running), daemon=True)
    sensor_worker = threading.Thread(target=sensor_task, args=(running,), daemon=True)
    heartbeat_worker = threading.Thread(target=heartbeat_task, args=(running,), daemon=True)
    command_processor_worker = threading.Thread(target=command_processor_task, args=(client, running,), daemon=True)

    # start threads
    sender_worker.start()
    sensor_worker.start()
    heartbeat_worker.start()
    command_processor_worker.start()
    
    unsent_queue = []   # store unsent messages safely

    try:
        # Send initial MasterInfo property update
        msg = create_master_info_msg()
        logger.debug("Queuing message: {message}")
        send_queue.put([MSGTYPE[1], msg])
            
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.warn("User canceled the program...")
        
    finally:
        running.clear()
        logger.close_logger()
        # sender_worker.join(timeout=2)
        # sensor_worker.join(timeout=1)
        # heartbeat_worker.join(timeout=1)
        time.sleep(2)  # wait for sender thread to exit
        client.disconnect()
        logger.info("Disconnected.")
        logger.info("Exiting.")
        
if __name__ == "__main__":
    main()