import serial
import time

PORT = "/dev/ttyUSB0"   # FTDI USB-to-RS485 adapter
BAUD = 19200           # Try 9600 or 19200 if no output

def open_serial():
    while True:
        try:
            ser = serial.Serial(
                port=PORT,
                baudrate=BAUD,
                timeout=0.5,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"[OK] Connected to {PORT} at {BAUD} baud")
            return ser
        except serial.SerialException:
            print("[WAIT] USB-RS485 adapter not found... retrying in 2 sec")
            time.sleep(2)

def main():
    ser = open_serial()
    buffer = ""

    print("---- RS485 Sniffer (Printer Mode) ----")
    print("Waiting for data...")

    while True:
        try:
            data = ser.read(128)   # read small chunks continuously
            if data:
                try:
                    decoded = data.decode("utf-8", errors="ignore")
                except:
                    decoded = str(data)

                buffer += decoded

                # Process line-by-line
                if "\n" in buffer:
                    lines = buffer.split("\n")
                    for line in lines[:-1]:   # each full line
                        clean = line.strip()
                        if clean:
                            print(f"[RECV] {clean}")
                    buffer = lines[-1]  # remainder (partial line)

        except KeyboardInterrupt:
            print("\nStopping sniffer.")
            break
        
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
