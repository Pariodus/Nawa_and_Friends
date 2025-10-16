import gpiod
import time

LED_PIN = 17
BUTTON_PIN = 27

chip = gpiod.Chip('gpiochip4')
led_line = chip.get_line(LED_PIN)
button_line = chip.get_line(BUTTON_PIN)

led_line.request(consumer="LED", type=gpiod.LINE_REQ_DIR_OUT)
button_line.request(consumer="Button", type=gpiod.LINE_REQ_DIR_IN)

led_state = 0      # 0 = OFF, 1 = ON
press_count = 0    # count how many presses

try:
    while True:
        button_state = button_line.get_value()

        if button_state == 1:
            press_count += 1
            led_state = 1 - led_state
            led_line.set_value(led_state)

            print(f"Button pressed {press_count} times")

            # Wait until button is released to avoid double count
            while button_line.get_value() == 1:
                time.sleep(0.02)

        time.sleep(0.02)  # debounce
finally:
    led_line.release()
    button_line.release()
