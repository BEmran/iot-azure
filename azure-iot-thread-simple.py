#!/usr/bin/env python3
import time
import json
import socket
import concurrent.futures
from azure.iot.device import ProvisioningDeviceClient, IoTHubDeviceClient, MethodResponse, Message
import threading
import queue
import yaml
 # custom module
import logger
from slave import Slave # custom module
import network
import my_azure
import find_ip_mac_only

CONFIG_PATH = "simple_config.yaml"
RUNNING = True
# ----------------------------------------------------
# GLOBALS
# ----------------------------------------------------
send_queue = queue.Queue()
CLIENT = None
SLAVE_READY_STATE = False
LED_USED = False
DEVICE_ID = "0"
HEARTBEAT_INTERVAL_SEC = 10.0
SLAVE_CONFIG = {"num": 0, "relay_gpio_line": 17, "power_off_delay_sec": 5.0, "slave_ip_address": ""}
LOG_CONFIG = {"print_level": "info", "log_level": "info", "log_dir": "logs"}

# ----------------------------------------------------
# change status
# ----------------------------------------------------  
def slave_status():
    global SLAVE_CONFIG
    if SLAVE_CONFIG["slave_ip_address"] == "":
        return "NOT_CONFIGURED"
    elif network.ping(SLAVE_CONFIG["slave_ip_address"]):
        return "CONNECTED"
    else:
        return "NOT_CONNECTED"
    
def led_status():
    if LED_USED:
        return "BUSY"
    else:
        return "READY"
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
        raise Runtimelogger.error(f"Cannot find configuration file")
    return cfg

def connection_string(config):
    global DEVICE_ID
    if "device_id" not in config or "symmetric_key" not in config or "id_scope" not in config:
        logger.error("Incomplete DPS configuration.")
        raise Runtimelogger.error(f"Cannot find connection string related configuration")
    DEVICE_ID = config["device_id"]
    id_scope = config["id_scope"]
    symmetric_key = config["symmetric_key"]
    logger.debug(f"Connection configuration parsed device_id={DEVICE_ID}, id_scope={id_scope}, symmetric_key={symmetric_key}")
    return my_azure.create_connection_str_from_dps(DEVICE_ID, id_scope, symmetric_key)

def parse_heartbeat_config(config):
    """Parse heartbeat configuration"""
    global HEARTBEAT_INTERVAL_SEC
    interval = int(config.get("heartbeat_interval_sec", HEARTBEAT_INTERVAL_SEC))
    if interval <= 0:
        logger.warn(f"Invalid heartbeat interval {interval}, using default {HEARTBEAT_INTERVAL_SEC}")
        HEARTBEAT_INTERVAL_SEC = interval
    logger.debug(f"Heartbeat interval: {HEARTBEAT_INTERVAL_SEC}")
    
def parse_log_config(config):
    """Parse system configuration"""
    
    LOG_CONFIG["log_level"] = str(config.get("log_level", LOG_CONFIG["log_level"])).upper()
    logger.debug(f"Log level set to: {LOG_CONFIG['log_level']}")
    
    LOG_CONFIG["print_level"] = str(config.get("print_level", LOG_CONFIG["print_level"])).upper()
    logger.debug(f"Print level set to: {LOG_CONFIG['print_level']}")
    
    LOG_CONFIG["log_dir"] = str(config.get("log_dir", LOG_CONFIG["log_dir"]))
    logger.debug(f"Log directory set to: {LOG_CONFIG['log_dir']}")
    
    logger.debug(f"System configuration parsed: {LOG_CONFIG}")

def parse_slave_config(config):
    """Get slave configuration"""
    global SLAVE_CONFIG
    num = config.get("num", SLAVE_CONFIG["num"])
    if num < 0:
        logger.warn(f"Invalid slave num {num}, using default {SLAVE_CONFIG['num']}")
        SLAVE_CONFIG["num"] = num
    
    power_off_delay_sec = float(config.get("power_off_delay_sec", SLAVE_CONFIG["power_off_delay_sec"]))
    if power_off_delay_sec < 0:
        logger.warn(f"Invalid power on delay {power_off_delay_sec}, using default {SLAVE_CONFIG['power_off_delay_sec']}")
        SLAVE_CONFIG["power_off_delay_sec"] = power_off_delay_sec

    relay_gpio_line = int(config.get("relay_gpio_line", SLAVE_CONFIG["relay_gpio_line"]))
    if relay_gpio_line < 0:
        logger.warn(f"Invalid relay GPIO line {relay_gpio_line}, using default {SLAVE_CONFIG['relay_gpio_line']}")
        SLAVE_CONFIG["relay_gpio_line"] = relay_gpio_line
        
    ip = str(config.get("slave_ip_address", SLAVE_CONFIG["slave_ip_address"]))
    if not ip:
        if config.get("search_for_slave_ip_address", False):
            logger.debug("Slave ip address is empty. Searching for slave IP address...")
            ip = find_ip_mac_only.find_vendor_ips_in_subnet("")
            if ip:
                logger.debug(f"Found slave IP address: {ip}")
            else:
                logger.warn("Could not find slave IP address on the network.")
        else:
            logger.warn(f"Slave ip address is empty, using default {SLAVE_CONFIG['slave_ip_address']}")
        SLAVE_CONFIG["slave_ip_address"] = ip
    
    logger.debug(f"Slave configuration parsed: {SLAVE_CONFIG}")

def apply_system_config():
    """Apply system configuration"""
    logger.set_log_level(LOG_CONFIG["log_level"])
    logger.set_print_level(LOG_CONFIG["print_level"])
    logger.set_logs_dir(LOG_CONFIG["log_dir"])
 
# ----------------------------------------------------
# creating messages
# ----------------------------------------------------
def create_heartbeat():
    payload = {
        "SlaveStatus": slave_status(),
        "LedStatus": led_status(),
    }
    return payload

def create_info_msg():
    global DEVICE_ID, SLAVE_CONFIG
    payload = {
        "DeviceID": DEVICE_ID,
        "DeviceIP": network.get_local_ip(), # str(socket.gethostbyname(socket.gethostname())),
        "SlaveIP": SLAVE_CONFIG["slave_ip_address"],
    }
    return payload

# ======================================================
# COMMAND PROCESSOR THREAD
# ======================================================
def restart_slave_task(delay_sec):
    global LED_USED
    if delay_sec is None or delay_sec < 0:
        delay_sec = 0
    logger.debug(f"Restarting slave will start in {delay_sec} seconds...")
    LED_USED = True
    time.sleep(delay_sec)
    
    Slave(
        relay_gpio_line=SLAVE_CONFIG["relay_gpio_line"],
        num=SLAVE_CONFIG["num"],
        debug=False
    ).power_cycle(off_duration=SLAVE_CONFIG["power_off_delay_sec"])
    
    LED_USED = False
    logger.debug("Slave restarted and ready.")
    
def stop_task():
    global RUNNING
    delay_sec = 3
    logger.debug(f"Stop Running in {delay_sec} seconds...")
    time.sleep(delay_sec)
    RUNNING = False
    
def restart_cmd(cmd_payload):
    logger.info("Restart command received.")
    delay = cmd_payload.get("delay", 0)
    reason = cmd_payload.get("reason", "unspecified")
    logger.debug(f"Restarting in {delay} seconds. Reason: {reason}")
    threading.Thread(target=restart_slave_task, args=(delay, )).start()
    return "restarted", 200

def stop_cmd():
    logger.info("Stop command received.")
    threading.Thread(target=stop_task).start()
    return "Recived", 999

def set_slave_ip_cmd(cmd_payload):
    global SLAVE_CONFIG
    logger.info("Set slave ip address.")
    SLAVE_CONFIG["slave_ip_address"] = str(cmd_payload.get("IP", 0))
    logger.debug(f"new ip address {SLAVE_CONFIG["slave_ip_address"]}")
    return "updated", 200

def command_processor_task(thread_running_event):
    global CLIENT
    logger.info("Command processor ready...")

    while thread_running_event.is_set():
        cmd_request = CLIENT.command_queue.get()  # waits automatically

        cmd_name = cmd_request.name
        payload = cmd_request.payload
        logger.debug(f"processing command {cmd_name} and payload {payload}")

        try:
            # COMMAND ROUTING
            if cmd_name == "RestartSlave":
                status, code = restart_cmd(payload)
            elif cmd_name == "SetSlaveIP":
                status, code = set_slave_ip_cmd(payload)
            elif cmd_name == "Stop":
                status, code = stop_cmd()
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
        CLIENT.send_method_response(response)

        logger.info(f"[CMD] Completed command {cmd_name}")

# ----------------------------------------------------
# SENDER TASK THREAD
# ----------------------------------------------------
def sender_task(thread_running_event):
    global CLIENT
    while thread_running_event.is_set():
        msg = send_queue.get()  # blocking wait for next message

        network.wait_until_connected()

        # Ensure Azure client is connected
        if not CLIENT.connect_to_iot_hub():
            logger.warn("Will retry sending message later...")
            time.sleep(5) # check_interval_sec
            send_queue.put(msg)  # Put back into queue
            continue

        # Try sending the message
        try:
            CLIENT.send_with_timeout(msg)
            
        except Exception as e:
            logger.error(f"send_message failed: {e}")
            logger.warn("Will retry sending message later...")
            time.sleep(5) # check_interval_sec
            send_queue.put(msg)  # Put back into queue

        time.sleep(0.1)  # prevent CPU spin
    
    logger.info("Sender worker thread exiting...")

# ----------------------------------------------------
# HEARTBEAT TASK THREAD – DIFFERENT RATE
# ----------------------------------------------------
def heartbeat_task(thread_running_event):
    global CLIENT
    last_time = 0
    while thread_running_event.is_set():
        now = time.time()
        if now - last_time >= HEARTBEAT_INTERVAL_SEC:
            last_time = now
            message = create_heartbeat()
            logger.debug(f"Queuing message: {message}")
            send_queue.put(my_azure.create_telementry_message_pair(message))
        time.sleep(0.1)

# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    global CLIENT
    start_time = time.time()
    logger.debug(f"Starting Azure IoT device client at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
    
    # parse configuration
    config = load_config()
    parse_heartbeat_config(config)
    parse_log_config(config)
    parse_slave_config(config)
    apply_system_config()

    network.wait_until_connected()
    conn_str = connection_string(config)
    CLIENT = my_azure.Client(conn_str)
    
    if not CLIENT.connect_to_iot_hub():
        logger.error("Could not connect to IoT Hub.")
        return  # Fail early if completely unable

    logger.info("System ready.")
    
    # Start background sender thread
    thread_running = threading.Event()
    thread_running.set()
    
    # create threads
    sender_worker = threading.Thread(target=sender_task, args=(thread_running,), daemon=True)
    heartbeat_worker = threading.Thread(target=heartbeat_task, args=(thread_running,), daemon=True)
    command_processor_worker = threading.Thread(target=command_processor_task, args=(thread_running,), daemon=True)

    # start threads
    sender_worker.start()
    heartbeat_worker.start()
    command_processor_worker.start()
    
    try:
        # Send initial MasterInfo property update
        msg = create_info_msg()
        logger.debug("Queuing message: {msg}")
        send_queue.put(my_azure.create_property_message_pair(msg))
            
        while RUNNING:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.warn("User canceled the program...")
        
    finally:
        thread_running.clear()
        logger.close_logger()
        sender_worker.join(timeout=2)
        heartbeat_worker.join(timeout=1)
        command_processor_worker.join(timeout=1)
        time.sleep(2)  # wait for sender thread to exit
        CLIENT.disconnect()
        logger.info("Disconnected.")
        logger.info("Exiting.")
        
if __name__ == "__main__":
    main()