import gpiod
from gpiod.line import Direction, Value
import time

# Define the GPIO chip and line number
chip_path = "/dev/gpiochip4"  # This might vary, check your system
gpio_line = 17  # Replace with your desired GPIO line number

# Configure the line settings
config = {
    gpio_line: gpiod.LineSettings(
        direction=Direction.OUTPUT,
        active_low=False,  # Set to True if active low, False for active high
        output_value=Value.ACTIVE
    )
}

# Request the GPIO line
req = gpiod.request_lines(chip_path, config=config)

delay = 2  # seconds
# To set the output value (e.g., turn on an LED)
req.set_value(gpio_line, Value.ACTIVE)  # Or Value.INACTIVE to turn off
time.sleep(delay)   
req.set_value(gpio_line, Value.INACTIVE)  # Turn off the LED
time.sleep(delay)
# Release the line when done
req.release()