#!/usr/bin/env python3
import socket
import subprocess
import platform
import logger

CHECK_INTERVAL = 5.0 # sec
# ----------------------------------------------------
# NETWORK CHECK
# ----------------------------------------------------

def ping(ip_address):
    """
    Pings a given IP address and returns True if reachable, False otherwise.
    """
    command = ["ping", "-c", "1", ip_address]

    try:
        # Execute the ping command
        # capture_output=True captures stdout and stderr
        # text=True decodes output as text
        # timeout sets a limit for the command execution
        logger.debug(f"trying to ping {ip_address}")
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)

        # Check the return code: 0 usually means success
        if result.returncode == 0:
            logger.debug(f"{ip_address} is reachable.")
            return True
        else:
            logger.debug(f"{ip_address} is unreachable. Output:\n{result.stdout}{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.debug(f"Ping to {ip_address} timed out.")
        return False
    except FileNotFoundError:
        logger.debug("Error: 'ping' command not found. Ensure it's in your system's PATH.")
        return False
    except Exception as e:
        logger.debug(f"An error occurred: {e}")
        return False

def is_connected(host_site="www.google.com", port=80):
    """
    Check internet connectivity by attempting to connect to a host.
    Default: Google DNS (8.8.8.8).
    Returns True if connection succeeds, False otherwise.
    """
    try:
        # DNS working?
        host = socket.gethostbyname(host_site)

        # TCP connectivity working?
        socket.setdefaulttimeout(CHECK_INTERVAL)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    
    except Exception as e:
        logger.error(f"Failed to connect to network: {e}")
        return False

def wait_until_connected():
    while not is_connected():
        logger.warn(f"No internet. Retrying in {CHECK_INTERVAL} sec...")
        time.sleep(CHECK_INTERVAL)
    
def main():
    
    timeout = 5.0 # sec
    wait_until_connected()
    print("Device is connected to internet")
 
    target_ip = "10.189.229.149" 
    print(f"result of pinging {ping(target_ip)}")
    
if __name__ == "__main__":
    main()