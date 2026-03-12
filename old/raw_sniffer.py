import serial
import time

PORT = "/dev/ttyUSB0"

baud_rates = [57600] #[9600, 19200, 38400, 57600, 115200]
parities = [serial.PARITY_EVEN]  # [serial.PARITY_NONE, serial.PARITY_EVEN, serial.PARITY_ODD]
stopbits = [serial.STOPBITS_TWO]

print("Starting auto-detect...\n")

while True:
    for baud in baud_rates:
        for parity in parities:
            for sb in stopbits:
                try:
                    print(f"Testing {baud} baud, parity={parity}, stopbits={sb}")
                    ser = serial.Serial(PORT, baud, timeout=0.5, parity=parity, stopbits=sb)

                    data = ser.read(64)
                    ser.close()
                    print("----------------------------------------Sample data:", data) 
                    if data and data != b'\x00' * len(data):
                        print(f"\n\n===== SUCCESS! =====")
                        print(f"Settings: baud={baud}, parity={parity}, stopbits={sb}")
                        print("Sample data:", data)
                        exit()
                except Exception as e:
                    pass

print("\nNo valid setting found. Try swapping A/B or check wiring.")
