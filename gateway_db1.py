#!/usr/bin/env python3
import os, time, json, serial, sqlite3, datetime, signal
from smbus2 import SMBus
from gpiozero import LED

# --- Config ---
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyAMA0")
BAUD, TIMEOUT = 115200, 1
I2C_BUS, BH1750_ADDR = 1, 0x23
DB_PATH = "gateway_db.db"

# LED config
LED_PIN = int(os.getenv("LED_PIN", "17"))  # GPIO18 (pin 12)
LUX_ON  = float(os.getenv("LUX_ON",  "40"))  # < 40 = ติด
LUX_OFF = float(os.getenv("LUX_OFF", "50"))  # > 50 = ดับ (hysteresis กันกะพริบ)

# --- DB Setup ---
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS readings(
  id INTEGER PRIMARY KEY,
  ts TEXT, temp_c REAL, tds_ppm REAL, water INT, lux REAL, raw TEXT
)""")
conn.commit()

def now(): return datetime.datetime.now().isoformat(timespec="seconds")
def insert(temp=None, tds=None, water=None, lux=None, raw=None):
    cur.execute("INSERT INTO readings(ts,temp_c,tds_ppm,water,lux,raw) VALUES(?,?,?,?,?,?)",
                (now(), temp, tds, water, lux, raw)); conn.commit()

def read_lux():
    with SMBus(I2C_BUS) as bus:
        bus.write_byte(BH1750_ADDR, 0x01)   # power on
        bus.write_byte(BH1750_ADDR, 0x07)   # reset
        bus.write_byte(BH1750_ADDR, 0x10)   # cont high res
        time.sleep(0.18)
        data = bus.read_i2c_block_data(BH1750_ADDR, 0x00, 2)
        return round(((data[0]<<8)|data[1]) / 1.2, 2)

# LED object
led = LED(LED_PIN)   # active-high
led.off()
led_state = False

def apply_led(lux_val):
    """ใช้ hysteresis: มืดมาก → ติด, สว่างพอ → ดับ"""
    global led_state
    if lux_val is None:
        return
    if not led_state and lux_val < LUX_ON:
        led.on();  led_state = True
        print(f"LED ON (lux={lux_val} < {LUX_ON})")
    elif led_state and lux_val > LUX_OFF:
        led.off(); led_state = False
        print(f"LED OFF (lux={lux_val} > {LUX_OFF})")

_running = True
def _shutdown(*_):
    global _running
    _running = False

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

with serial.Serial(SERIAL_PORT, BAUD, timeout=TIMEOUT) as ser:
    ser.reset_input_buffer()
    print("Listening on", SERIAL_PORT)
    try:
        while _running:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            try:
                if line.startswith("{") and line.endswith("}"):
                    d = json.loads(line)
                    lux = read_lux()
                    print(f"JSON Temp={d.get('temp_c')} TDS={d.get('tds_ppm')} Water={d.get('water')} Lux={lux}")
                    insert(d.get("temp_c"), d.get("tds_ppm"), d.get("water"), lux, line)
                    apply_led(lux)

                elif line.lower().startswith("water:"):
                    water = int(line.split(":",1)[1])
                    lux = read_lux()
                    print(f"TEXT Water={water} Lux={lux}")
                    insert(water=water, lux=lux, raw=line)
                    apply_led(lux)

                else:
                    # บรรทัดอื่น ๆ เก็บ raw ไว้เผื่อ debug
                    print("RAW", line)
                    insert(raw=line)

            except Exception as e:
                print("Error:", e)

    finally:
        led.off()
        conn.close()
        print("Closed DB & LED off. Bye.")
