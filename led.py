from relay import Relay
import time
import signal
import sys

class LED:
    def __init__(self, gpio_line: int, name: str, debug: bool = False):
        self.relay = Relay(gpio_line, debug=debug)
        self.name = name
        self.debug = debug
        self.debug_print(f"[LED][{self.name}]: initialized")
        
    def turn_on(self):
        self.debug_print(f"[LED][{self.name}]: Turning ON the LED device.")
        self.relay.turn_on()  # Assuming inactive LOW turns ON the LED
        
    def turn_off(self):
        self.debug_print(f"[LED][{self.name}]: Turning OFF the LED device.")
        self.relay.turn_off()  # Assuming inactive LOW turns OFF the LED
        
    def debug_print(self, message: str):
        if self.debug:
            print(message)
                 
    def __exit__(self):
        """
        This method is called when the instance is about to be destroyed
        by the garbage collector.
        """
        self.turn_off()
        
if __name__ == "__main__":
    import time
    LED = LED(gpio_line=3, name='Network', debug=True)
        
    try:
        while True:
            LED.turn_on()
            time.sleep(1)
            LED.turn_off()
            time.sleep(1)
    except KeyboardInterrupt:
        LED.turn_off()