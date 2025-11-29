from relay import Relay
import time

class Slave:
    def __init__(self, relay_gpio_line: int, num: int, debug: bool = False):
        self.relay = Relay(relay_gpio_line, debug=debug)
        self.num = num
        self.debug = debug
        self.debug_print(f"[Slave][#{self.num}]: initialized")
        
    def power_cycle(self, off_duration: int = 5):
        self.debug_print(f"[Slave][#{self.num}]: Powering OFF the slave device.")
        self.relay.turn_on()  # Assuming active HIGH turns OFF the slave
        time.sleep(off_duration)
        self.debug_print(f"[Slave][#{self.num}]: Powering ON the slave device.")
        self.relay.turn_off()  # Assuming inactive LOW turns ON the slave
        
    def debug_print(self, message: str):
        if self.debug:
            print(message)

if __name__ == "__main__":
    slave = Slave(relay_gpio_line=17, num=0, debug=True)
    slave.power_cycle(off_duration=5)