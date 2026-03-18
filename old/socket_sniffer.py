import socket
from datetime import datetime
import os

HOST = ""               # Listen on all network interfaces
PORT = 5005             # Device port setting
LOG_FILE = "socket_log.txt"

def log_to_file(text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {text}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, PORT))
    sock.listen(1)

    print(f"[OK] Socket sniffer listening on port {PORT}")
    print(f"[LOG] Logging to: {os.path.abspath(LOG_FILE)}")
    print("Waiting for device connection...\n")

    while True:
        conn, addr = sock.accept()
        print(f"[CONNECTED] Device at {addr}")
        log_to_file(f"CONNECTED from {addr}")

        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    print("[DISCONNECTED] Device closed connection")
                    log_to_file("DISCONNECTED")
                    break

                try:
                    text = data.decode("utf-8", errors="ignore").strip()
                except:
                    text = str(data)

                print(f"[RECV] {text}")
                log_to_file(text)

        except Exception as e:
            print(f"[ERROR] {e}")
            log_to_file(f"ERROR: {e}")

        finally:
            conn.close()

if __name__ == "__main__":
    start_server()