import time
import board
import logger 
from adafruit_ads1x15 import ADS1115, AnalogIn, ads1x15

# Configuration parameters
# gain values: 1=±4.096V, 2=±2.048V, 4=±1.024V, 8=±0.512V, 16=±0.256V
GAIN = 2
# data rate options: 8, 16, 32, 64, 128, 250, 475, 860 samples per second
DATA_RATE = 64
# window duration for reliable detection (seconds)
WINDOW_SECONDS = 2.0
# numebr of blocks 
NUM_BLOCKS = 5
# Adjust after observing your OFF/ON readings.
# Example:
# OFF Vpp maybe 0.005 to 0.02 V
# ON  Vpp maybe 0.3 to 1.0 V
CURRENT_THRESHOLD = 0.10

# In each 30-second window, require this fraction of blocks to detect current.
# 0.60 means at least 60% of the 0.5-second blocks must be above threshold.
DETECTION_RATIO = 0.60

class CurentSensing():
    def __init__(self, gain=GAIN, data_rate=DATA_RATE):
        """_summary_
        Args:
            gain (int, optional): _description_. Defaults to 2.
            data_rate (int, optional): _description_. Defaults to 64.
        """
        # Create I2C bus
        i2c = board.I2C()

        # Create ADS1115 object
        self.ads = ADS1115(i2c, address=0x48)

        # Set gain and data rate
        self.ads.gain = gain
        self.ads.data_rate = data_rate

        # Differential input A0 - A1
        self.chan = AnalogIn(self.ads, ads1x15.Pin.A0, ads1x15.Pin.A1)
        self.last_vpp = 0

    def read_vpp(self, window_seconds=WINDOW_SECONDS, debug=False):
        """
        Reads ADS1115 differential voltage for a short block and returns:
        - vpp: peak-to-peak voltage
        - max_abs: maximum absolute voltage
        - number of samples
        """
        values = []
        end_time = time.time() + window_seconds
        while time.time() < end_time:
            values.append(self.chan.voltage)
        vpp = max(values) - min(values)
        max_abs = max(abs(v) for v in values)
        n = len(values)
        if debug:
            print(f"Vpp={vpp:.3f}V , MaxAbs={max_abs:.3f}V , #samples={n}")
        return vpp, max_abs, n
    
    def is_current_detected(self, threshold=CURRENT_THRESHOLD, window_seconds=WINDOW_SECONDS, debug=False):
        try:
            vpp, max_abs, n = self.read_vpp(window_seconds=window_seconds, debug=debug)
        except Exception as e:
            print(f"Error occurred while reading Vpp: {e}")
            vpp = self.last_vpp  # Use last known Vpp if read fails
        self.last_vpp = vpp  # Update last known Vpp
        return vpp > threshold

class ReliableCurrentSensing(CurentSensing):
    def __init__(self, gain=GAIN, data_rate=DATA_RATE, num_blocks=NUM_BLOCKS, window_seconds=WINDOW_SECONDS):
        super().__init__(gain=gain, data_rate=data_rate)
        self.num_blocks = num_blocks
        self.window_seconds = window_seconds

    def is_current_detected_for_window(self, debug=False):
        """
        Returns one True/False decision for the full window.
        The window is divided into smaller blocks.
        Current is detected if enough blocks exceed VPP_THRESHOLD.
        """
        block_results = []
        start_time = time.time()
        for i in range(self.num_blocks):
            detected_in_block = self.is_current_detected(window_seconds=self.window_seconds, debug=debug)
            block_results.append(detected_in_block)
            
        detected_blocks = sum(block_results)        
        ratio = detected_blocks / self.num_blocks
        return ratio >= DETECTION_RATIO

if __name__ == "__main__":
    sensor = ReliableCurrentSensing(gain=GAIN, data_rate=DATA_RATE, num_blocks=3, window_seconds=1)
    
    try:
        while True:
            current_detected = sensor.is_current_detected_for_window(debug=True)
            print(f"current_detected={current_detected}")
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopped.") 