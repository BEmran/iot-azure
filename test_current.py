import gpiod
from gpiod.line import Direction, Bias, Value

DEFAULT_CHIP_PATH = "/dev/gpiochip0"  # Usually gpiochip0 on Raspberry Pi 3


class InputPin:
    def __init__(self, gpio_line: int, chip_path: str = DEFAULT_CHIP_PATH, debug: bool = False):
        self.gpio_line = gpio_line
        self.chip_path = chip_path
        self.debug = debug
        self.req = None

        config = {
            self.gpio_line: gpiod.LineSettings(
                direction=Direction.INPUT,
                # bias=Bias.PULL_UP
            )
        }

        self.req = gpiod.request_lines(
            self.chip_path,
            consumer="lm393_reader",
            config=config
        )

        self.debug_print(
            f"[InputPin] Initialized GPIO line {self.gpio_line} on {self.chip_path}"
        )

    def debug_print(self, message: str):
        if self.debug:
            print(message)

    def read(self) -> int:
        value = self.req.get_value(self.gpio_line)

        # Convert gpiod Value enum to normal integer 0 or 1
        if value == Value.ACTIVE:
            result = 1
        else:
            result = 0

        self.debug_print(
            f"[InputPin] Read value {result} from GPIO line {self.gpio_line}"
        )

        return result

    def release(self):
        if self.req is not None:
            self.req.release()
            self.req = None
            self.debug_print(
                f"[InputPin] Released GPIO line {self.gpio_line}"
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def __del__(self):
        self.release()


if __name__ == "__main__":
    from time import sleep

    PIN = 17  # GPIO17, physical pin 11

    with InputPin(PIN, debug=True) as sensor:
        while True:
            value = sensor.read()
            print("LM393 digital value:", value)
            sleep(0.5)