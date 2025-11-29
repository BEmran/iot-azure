import gpiod
from gpiod.line import Direction, Value

DEFAULT_CHIP_PATH = "/dev/gpiochip4"

class Relay:
    def __init__(self, gpio_line: int, chip_path: str = DEFAULT_CHIP_PATH, debug: bool = False):
        self.gpio_line = gpio_line
        self.debug = debug
        
        config = {
            self.gpio_line: gpiod.LineSettings(
                direction=Direction.OUTPUT,
                active_low=False,  # Set to True if active low, False for active high
                output_value=Value.INACTIVE
            )
        }
        self.req = gpiod.request_lines(chip_path, config)
        
        self.debug_print(f"[Relay] Initializing Relay on GPIO line {self.gpio_line} at {chip_path}")
        
    def debug_print(self, message: str):
        if self.debug:
            print(message)

    def turn_on(self):
        self.req.set_value(self.gpio_line, Value.ACTIVE)
        self.debug_print(f"[Relay] Relay on GPIO line {self.gpio_line} turned ON")

    def turn_off(self):
        self.req.set_value(self.gpio_line, Value.INACTIVE)
        self.debug_print(f"[Relay] Relay on GPIO line {self.gpio_line} turned OFF")
        
    def release(self):
        self.req.release()
        self.debug_print(f"[Relay] Released GPIO line {self.gpio_line}")
        
    def __exit__(self):
        """
        This method is called when the instance is about to be destroyed
        by the garbage collector.
        """
        self.release()

if __name__ == "__main__":
    import time

    # Define the GPIO chip and line number
    gpio_line = 17
    relay = Relay(gpio_line, debug=True)
    delay = 2  # seconds
    
    relay.turn_on()
    time.sleep(delay)   
    relay.turn_off()
