#!/usr/bin/env python3
import time
import json
import concurrent.futures
from azure.iot.device import ProvisioningDeviceClient, IoTHubDeviceClient, MethodResponse, Message
import threading
import queue
import logger # custom logger module

# ----------------------------------------------------
# GLOBALS
# ----------------------------------------------------
MSGTYPE = ["TELEMETRY", "PROPERTY"]

RECONNECT_INTERVAL = 5.0 # sec
RESEND_INTERVAL = 15.0 # sec

def prepaere_telemetry_message(message):
    telemetry = Message(json.dumps(message))
    telemetry.content_type = "application/json"
    telemetry.content_encoding = "utf-8"
    return telemetry

def create_telementry_message_pair(message):
    return {"type":MSGTYPE[0], "msg":prepaere_telemetry_message(message)}

def create_property_message_pair(message):
    return {"type":MSGTYPE[1], "msg":message}

def create_connection_str_from_dps(device_id, id_scope, symmetric_key):
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

class Client():
    def __init__(self, conn_str):
        
        logger.info("Creating new IoTHubDeviceClient...")
        self.client = IoTHubDeviceClient.create_from_connection_string(conn_str)
        self.lock = threading.Lock()
        self.command_queue = queue.Queue()
            
    def send_with_timeout(self, message):
        if message is None:
            logger.warn("No message to send.")
            return True  # nothing to send
        
        logger.debug(f"Sending: {message}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            if message["type"] == MSGTYPE[0]:  # telemetry
                future = executor.submit(self.client.send_message, message["msg"])
                
            elif message["type"] == MSGTYPE[1]:  # propertyUpdate
                future = executor.submit(self.client.patch_twin_reported_properties, message["msg"])
            
            try:
                future.result(timeout=RESEND_INTERVAL)
                logger.info("Message sent successfully.")
                return True

            except concurrent.futures.TimeoutError as exc:
                logger.error(f"send_message timed out: {exc} after {RESEND_INTERVAL} sec")
                return False

            except Exception as e:
                logger.error(f"send_message failed: {e}")
                return False
            
    def connect_to_iot_hub(self):
        with self.lock:
            if not self.client.connected:
                try:
                    logger.info("Connecting to Azure IoT Hub...")
                    self.client.connect()
                    logger.info("Successfully connected to IoT Hub.")

                except Exception as e:
                    logger.error(f"Azure connect failed: {e}")
                    time.sleep(RECONNECT_INTERVAL)
            
        self.client.on_method_request_received = self.command_handler
        return True

    def command_handler(self, method_request):
        """
        Handler for incoming direct methods (commands).
        """
        logger.info(f"Received command: {method_request.name}")
        logger.debug(f"Received command {method_request.name} with payload {method_request.payload}")
        # Push the request to the queue
        self.command_queue.put(method_request)
    
    def send_method_response(self, response):
        self.client.send_method_response(response)
        
    def disconnect(self):
        self.client.disconnect()
        logger.info("Disconnected.")
        
    def __exit__(self):
        self.disconnect()
        
# ----------------------------------------------------
# MAIN
# ----------------------------------------------------
def main():
    id_scope= "0ne01093627"
    device_id= "01"
    symmetric_key= "C80Pr2/HQy0PQxt8oqUQbRgRihYqkxd5MJbeSZictwQ="
    conn_str = create_connection_str_from_dps(device_id, id_scope, symmetric_key)
    client = Client(conn_str)
    
    if not client.connect_to_iot_hub():
        logger.error("Could not connect to IoT Hub.")
        return  # Fail early if completely unable
    logger.info("connected successfully.")
    client.disconnect()
    
if __name__ == "__main__":
    main()