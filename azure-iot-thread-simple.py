#!/usr/bin/env python3
import time
import json
import socket
import concurrent.futures
from azure.iot.device import ProvisioningDeviceClient, IoTHubDeviceClient, MethodResponse, Message
import threading
import queue
import yaml
import subprocess
import git
import os
from pathlib import Path
import shutil

 # custom module
import logger
from slave import Slave # custom module
from led import LED # custom module
from sense_current import ReliableCurrentSensing # custom module
import network
import my_azure
import find_ip_mac_only

HEARTBEAT_SEQUENCE_NUMBER = 0

AZURE_CONFIG_PATH = "azure_config.yaml"
APP_CONFIG_PATH = "app_config.yaml"
RUNNING = True
STATE = "UNCONFIGURED"
POWER_STATE = True # assume power is on at start, will be updated by power sensing task
# ----------------------------------------------------
# GLOBALS
# ----------------------------------------------------
send_queue = queue.Queue()
CLIENT = None
REALY_USED = False
DEVICE_ID = "0"
DEPLOYMENT_DATE = "2024-01-01" # TODO: get from config or env variable
HEARTBEAT_INTERVAL_SEC = 10.0
SLAVE_CONFIG = {"num": 0, "relay_gpio_line": 27, "power_off_delay_sec": 5.0, "slave_ip_address": "", "detect_power": False}
LED_CONFIG = {"network_gpio_line": 4, "azure_gpio_line": 17}
LOG_CONFIG = {"print_level": "info", "log_level": "info", "log_dir": "logs"}
BRANCH_NAME = "main"

# ----------------------------------------------------
# helpper
# # ----------------------------------------------------

from pathlib import Path
import shutil
import git
import subprocess

BRANCH_NAME = "stable"
REPO_PATH = Path("/opt/iot-azure")

def git_pull_repo():
    try:
        logger.debug(f"Using repo path: {REPO_PATH}")

        repo = git.Repo(REPO_PATH)
        origin = repo.remotes.origin

        try:
            stash_result = repo.git.stash("push", "-u", "-m", "auto-stash-before-update")
            logger.debug(stash_result)
            if "No local changes to save" not in stash_result:
                repo.git.stash("drop")
                logger.debug("Dropped temporary auto-stash")
                
        except Exception as stash_err:
            logger.warn(f"Stash step failed: {stash_err}")
        except Exception as drop_err:
            logger.warn(f"Could not drop stash: {drop_err}")
            
        origin.fetch()
        repo.git.checkout(BRANCH_NAME)
        repo.git.reset("--hard", f"origin/{BRANCH_NAME}")
        logger.info(f"Successfully updated {BRANCH_NAME} in {REPO_PATH}")

        local_cfg = Path("/opt/site_provision/config/azure_config.yaml")
        repo_cfg = REPO_PATH / "azure_config.yaml"

        if local_cfg.exists():
            shutil.copy2(local_cfg, repo_cfg)
            logger.info(f"Restored local config: {local_cfg} -> {repo_cfg}")
        else:
            logger.warn(f"Local config not found: {local_cfg}")

    except Exception as e:
        logger.warn(f"Failed to update branch: {e}")

# ----------------------------------------------------
# change status
# ----------------------------------------------------
def slave_status():
    global SLAVE_CONFIG, POWER_STATE
    ip = SLAVE_CONFIG["slave_ip_address"]
    if ip == "":
        return "UNCONFIGURED"
    
    if SLAVE_CONFIG["detect_power"] and not POWER_STATE:
        return "DOWN"
    
    if network.ping(ip):
        return "ONLINE"
    else:
        return "OFFLINE"


# ----------------------------------------------------
# CONFIGURAION
# ----------------------------------------------------
def load_config(config_path):
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise RuntimeError("Cannot find configuration file")
    return cfg

def connection_string(config):
    global DEVICE_ID
    # priority to connection string
    if "connection_string" in config:
        logger.debug(f"Using conenction string to connect to azure, {config['connection_string']}")

    if "device_id" not in config:
        logger.error("Incomplete DPS configuration. missing device_id")
        raise RuntimeError("Cannot find connection string related configuration")
    DEVICE_ID = config["device_id"]
    
    logger.debug(f"Connection configuration parsed device_id={DEVICE_ID}")
    
    return config["connection_string"]


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

    relay_gpio = int(config.get("relay_gpio_line", SLAVE_CONFIG["relay_gpio_line"]))
    if relay_gpio < 0:
        logger.warn(f"Invalid relay GPIO line {relay_gpio}, using default {SLAVE_CONFIG['relay_gpio_line']}")
    SLAVE_CONFIG["relay_gpio_line"] = relay_gpio
        
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
    
    SLAVE_CONFIG["detect_power"] = bool(config.get("detect_power", SLAVE_CONFIG["detect_power"]))
    
    logger.debug(f"Slave configuration parsed: {SLAVE_CONFIG}")

def parse_led_config(config):
    """Get led configuration"""
    global LED_CONFIG
    network_gpio = int(config.get("network_led_gpio_line", LED_CONFIG["network_gpio_line"]))
    azure_gpio = int(config.get("azure_led_gpio_line", LED_CONFIG["azure_gpio_line"]))
    if network_gpio < 0:
        logger.warn(f"Invalid network GPIO line {network_gpio}, using default {LED_CONFIG['network_gpio_line']}")
    LED_CONFIG["network_gpio_line"] = network_gpio
        
    if azure_gpio < 0:
        logger.warn(f"Invalid azure GPIO line {azure_gpio}, using default {LED_CONFIG['azure_gpio_line']}")
    LED_CONFIG["azure_gpio_line"] = azure_gpio

def parse_general_config(config):
    """Get general configuration"""
    global BRANCH_NAME
    branch_name = str(config.get("branch_name", BRANCH_NAME))
    if branch_name == "":
        logger.warn(f"Invalid branch name '{branch_name}', using default '{BRANCH_NAME}'")
    BRANCH_NAME = branch_name

def apply_system_config():
    """Apply system configuration"""
    logger.set_log_level(LOG_CONFIG["log_level"])
    logger.set_print_level(LOG_CONFIG["print_level"])
    logger.set_logs_dir(LOG_CONFIG["log_dir"])
 
# ----------------------------------------------------
# creating messages
# ----------------------------------------------------
def create_heartbeat(slave_status_str):
    global HEARTBEAT_SEQUENCE_NUMBER
    HEARTBEAT_SEQUENCE_NUMBER += 1
    payload = {
        "deviceUtcTs": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sequenceNumber": HEARTBEAT_SEQUENCE_NUMBER,
        "SlaveStatus": slave_status_str,
    }
    return payload

def create_info_msg():
    global SLAVE_CONFIG, DEVICE_ID, DEPLOYMENT_DATE 
    payload = {
        "device_id": DEVICE_ID,
        "deploymentDate": DEPLOYMENT_DATE,
        "rpiIp": network.get_local_ip(), # str(socket.gethostbyname(socket.gethostname())),
        "slaveIp": SLAVE_CONFIG["slave_ip_address"],
    }
    return payload

# ======================================================
# COMMAND PROCESSOR THREAD
# ======================================================
def restart_slave_task(delay_sec):
    global REALY_USED
    if delay_sec is None or delay_sec < 0:
        delay_sec = 0
    logger.debug(f"Restarting slave will start in {delay_sec} seconds...")
    REALY_USED = True
    time.sleep(delay_sec)
    
    Slave(
        relay_gpio_line=SLAVE_CONFIG["relay_gpio_line"],
        num=SLAVE_CONFIG["num"],
        debug=False
    ).power_cycle(off_duration=SLAVE_CONFIG["power_off_delay_sec"])
    
    REALY_USED = False
    logger.debug("Slave restarted and ready.")
    
def stop_task():
    global RUNNING
    delay_sec = 3
    logger.debug(f"Stop Running in {delay_sec} seconds...")
    time.sleep(delay_sec)
    RUNNING = False
      
def restart_device_task(thread_running_event):
    delay_min = 1
    logger.debug(f"Restarting in {delay_min} minutes...")
    # 'sudo shutdown -r +X' reboots the system in minutes
    command = f"sudo shutdown -r +{delay_min}"
    subprocess.run(command.split())
    thread_running_event.clear()  # signal threads to stop
      
def update_repo_task():
    logger.debug("Updating repository...")
    git_pull_repo();
         
def reboot_slave_cmd(cmd_payload):
    global STATE
    logger.info("Restart command received.")
    delay = 1
    reason = ""
    # try:
    #     # TODO: add dekay and reson to command to parse
    #     delay = float(cmd_payload.get("delay"))
    #     reason = str(cmd_payload.get("reason"))
    # except Exception as e:
    #     logger.warn(f"Processing error: {e}") 
    if REALY_USED:
        logger.warn("Slave is already being restarted. Ignoring this command.")
        return True, "Slave is busy restarting", -1
    logger.debug(f"Restarting in {delay} seconds. Reason: {reason}")
    threading.Thread(target=restart_slave_task, args=(delay, )).start()
    return True, "Reboot Success", 200

def stop_cmd():
    logger.info("Stop command received.")
    threading.Thread(target=stop_task).start()
    return True, "Recived", 200

def restart_device_cmd(thread_running_event):
    logger.info("Restart Device command received.")
    threading.Thread(target=restart_device_task, args=(thread_running_event,)).start()
    return True, "Recived", 200

def update_repo_cmd():
    logger.info("Update repo command received.")
    threading.Thread(target=update_repo_task).start()
    return True, "Recived", 200

def set_slave_ip_cmd(cmd_payload):
    global SLAVE_CONFIG
    logger.info("Set slave ip address.")
    
    if not "IP" in cmd_payload:
        logger.debug(f"Missing slave IP address")
        return False, "Missing IP Tag", 405
        
    try:
        new_ip = str(cmd_payload.get("IP"))
    except Exception as e:
        logger.warn(f"Processing error: {e}") 
        return False, "failed to parse ip address", 404
    
    if network.is_valid_ip(new_ip):
        SLAVE_CONFIG["slave_ip_address"] = new_ip
        logger.debug(f"new slave ip address {SLAVE_CONFIG["slave_ip_address"]}")
        return True, "Updated", 200
    else:
        logger.debug(f"The requested slave ip address {new_ip} is not valid")
        return False, "Not valid ip address", 406

def command_processor_task(thread_running_event):
    global CLIENT
    logger.info("Command processor ready...")

    while thread_running_event.is_set():
        cmd_request = CLIENT.command_queue.get()  # waits automatically

        cmd_name = cmd_request.name
        payload = cmd_request.payload
        logger.debug(f"processing method name {cmd_name} and payload {payload}")

        try:
            # COMMAND ROUTING
            if cmd_name == "reboot_slave":
                success, message, code = reboot_slave_cmd(payload)
            elif cmd_name == "configure_slave_ip":
                success, message, code = set_slave_ip_cmd(payload)
            elif cmd_name == "Stop":
                success, message, code = stop_cmd()
            elif cmd_name == "restart_device":
                success, message, code = restart_device_cmd(thread_running_event)
            elif cmd_name == "update_repo":
                success, message, code = update_repo_cmd()
            else:
                logger.warn(f"Unknown command {cmd_name}")
                success, message, code = False, "Unknown command", 404

        except Exception as e:
            logger.error(f"Processing error: {e}")
            success, message, code = False, "error", 500

        # SEND COMMAND RESPONSE
        response_payload = {"success":success, "message":message, "device_id":CLIENT.device_id}
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
    global CLIENT # TODO: check if this is needed ?!
    last_time = 0
    while thread_running_event.is_set():
        now = time.time()
        if now - last_time >= HEARTBEAT_INTERVAL_SEC:
            last_time = now
            message = create_heartbeat(slave_status_str=slave_status())
            logger.debug(f"Queuing message: {message}")
            send_queue.put(my_azure.create_telementry_message_pair(message))
        time.sleep(0.1)
        
# ----------------------------------------------------
# LED TASK THREAD – DIFFERENT RATE
# ----------------------------------------------------
def led_task(thread_running_event):
    global CLIENT, LED_CONFIG
    network_led = LED(gpio_line=LED_CONFIG["network_gpio_line"], name="Network", debug=False)
    azure_led = LED(gpio_line=LED_CONFIG["azure_gpio_line"], name="Azure", debug=False)
    while thread_running_event.is_set():
        if network.is_connected(debug=False):
            network_led.turn_on()
        else:
            network_led.turn_off()
        if CLIENT and CLIENT.is_connected_to_iot_hub(debug=False):
            azure_led.turn_on()
        else:
            azure_led.turn_off()
        time.sleep(1)
    network_led.turn_off()
    azure_led.turn_off()
    
# ----------------------------------------------------
# LED TASK THREAD – DIFFERENT RATE
# ----------------------------------------------------
def power_task(thread_running_event):
    global POWER_STATE
    sensor = ReliableCurrentSensing()
    while thread_running_event.is_set():
        if sensor.is_current_detected_for_window(debug=False):
            POWER_STATE = True
            logger.debug("Current detected. Power state ON.")
        else:
            POWER_STATE = False
            logger.debug("No current detected. Power state OFF.")
        time.sleep(15)  # check every 15 seconds
# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    global CLIENT
    start_time = time.time()
    logger.debug(f"Starting Azure IoT device client at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
    
    # parse configuration
    app_config = load_config(config_path=APP_CONFIG_PATH)
    parse_log_config(app_config)
    apply_system_config()
    parse_heartbeat_config(app_config)
    parse_led_config(app_config)
    parse_general_config(app_config)

    azure_config = load_config(config_path=AZURE_CONFIG_PATH)
    parse_slave_config(azure_config)
    try:
        
        # Start background sender thread
        thread_running_event = threading.Event()
        thread_running_event.set()
        # create threads
        sender_worker = threading.Thread(target=sender_task, args=(thread_running_event,), daemon=True)
        heartbeat_worker = threading.Thread(target=heartbeat_task, args=(thread_running_event,), daemon=True)
        command_processor_worker = threading.Thread(target=command_processor_task, args=(thread_running_event,), daemon=True)
        led_worker = threading.Thread(target=led_task, args=(thread_running_event,), daemon=True)
        power_worker = threading.Thread(target=power_task, args=(thread_running_event,), daemon=True)
        
        # start debug thread
        led_worker.start()
        
        network.wait_until_connected()
        conn_str = connection_string(azure_config)
        CLIENT = my_azure.Client(conn_str)
        
        if not CLIENT.connect_to_iot_hub():
            logger.error("Could not connect to IoT Hub.")
            return  # Fail early if completely unable

        logger.info("System ready.")
        
        # start threads
        sender_worker.start()
        heartbeat_worker.start()
        command_processor_worker.start()
        power_worker.start()
    
        # Send initial MasterInfo property update
        msg = create_info_msg()
        send_queue.put(my_azure.create_property_message_pair(msg))
            
        while RUNNING:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.warn("User canceled the program...")
        
    finally:
        thread_running.clear()
        logger.close_logger()
        CLIENT.disconnect()
        led_worker.join(timeout=1)
        sender_worker.join(timeout=2)
        heartbeat_worker.join(timeout=1)
        command_processor_worker.join(timeout=1)
        power_worker.join(timeout=1)
        time.sleep(2)  # wait for sender thread to exit
        logger.info("Disconnected.")
        logger.info("Exiting.")
        
if __name__ == "__main__":
    main()
