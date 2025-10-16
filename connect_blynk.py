#!/usr/bin/env python3
import os, time, json, serial, sqlite3, datetime, signal
from smbus2 import SMBus

# ---- Blynk (env var! do NOT hardcode) ----
import requests
BLYNK_TOKEN = os.getenv("BLYNK_TOKEN")  # export BLYNK_TOKEN=...
BLYNK_ENDPOINT = "https://blynk.cloud/external/api/batch/update"

# ---- Virtual pins (outputs to app) ----
V_TEMP  = 1   # °C
V_TDS   = 2   # ppm
V_WATER = 0   # water value
V_LUX   = 3   # lux

# ---- Config ----
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyAMA0")
BAUD, TIMEOUT = 115200, 1
I2C_BUS, BH1750_ADDR = 1, 0x23
DB_PATH = "gateway_db.db"

# LED config (GPIO numbering = BCM by default in gpiozero)
LED_PIN = int(os.getenv("LED_PIN", "17"))  # BCM18 (physical pin 12)
LUX_ON  = float(os.getenv("LUX_ON",  "40"))  # < 40 = ON
LUX_OFF = float(os.getenv("LUX_OFF", "50"))  # > 50 = OFF (hysteresis)

# ---- DB Setup ----
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS readings(
  id INTEGER PRIMARY KEY,
  ts TEXT, temp_c REAL, tds_ppm REAL, water INT, lux REAL, raw TEXT
)""")
conn.commit()

def now():
    return datetime.datetime.now().isoformat(timespec="seconds")

def insert(temp=None, tds=None, water=None, lux=None, raw=None):
    cur.execute(
        "INSERT INTO readings(ts,temp_c,tds_ppm,water,lux,raw) VALUES(?,?,?,?,?,?)",
        (now(), temp, tds, water, lux, raw)
    )
    conn.commit()

# ---- Sensors ----
def read_lux():
    try:
        with SMBus(I2C_BUS) as bus:
            bus.write_byte(BH1750_ADDR, 0x01)   # power on
            bus.write_byte(BH1750_ADDR, 0x07)   # reset
            bus.write_byte(BH1750_ADDR, 0x10)   # continuous high-res
            time.sleep(0.18)
            data = bus.read_i2c_block_data(BH1750_ADDR, 0x00, 2)
            return round(((data[0] << 8) | data[1]) / 1.2, 2)
    except Exception as e:
        print("BH1750 read error:", e)
        return None

# ---- LED ----
# If you prefer pigpio (recommended on Pi 5):
#   sudo apt-get install -y pigpio python3-pigpio && sudo systemctl enable --now pigpiod
#   from gpiozero import LED
#   from gpiozero.pins.pigpio import PiGPIOFactory
#   led = LED(LED_PIN, pin_factory=PiGPIOFactory())
from gpiozero import LED
led = LED(LED_PIN)  # active-high, BCM numbering
led.off()
led_state = False

def apply_led(lux_val):
    """Hysteresis: turn ON when really dark, turn OFF when bright enough."""
    global led_state
    if lux_val is None:
        return
    if not led_state and lux_val < LUX_ON:
        led.on();  led_state = True
        print(f"LED ON (lux={lux_val} < {LUX_ON})")
    elif led_state and lux_val > LUX_OFF:
        led.off(); led_state = False
        print(f"LED OFF (lux={lux_val} > {LUX_OFF})")

# ---- Graceful shutdown ----
_running = True
def _shutdown(*_):
    global _running
    _running = False
signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# ---- Blynk helper ----
_last_blynk_send = 0.0
_min_interval_s = 1.0  # simple throttle to avoid spamming

def blynk_update(temp=None, tds=None, water=None, lux=None):
    global _last_blynk_send
    if not BLYNK_TOKEN:
        return  # silently skip if no token set

    # throttle
    now_ts = time.time()
    if now_ts - _last_blynk_send < _min_interval_s:
        return

    # only include available values
    payload = {}
    if water is not None: payload[f"V{V_WATER}"] = water
    if temp  is not None: payload[f"V{V_TEMP}"]  = temp
    if tds   is not None: payload[f"V{V_TDS}"]   = tds
    if lux   is not None: payload[f"V{V_LUX}"]   = lux
    if not payload:
        return

    try:
        r = requests.get(BLYNK_ENDPOINT, params={"token": BLYNK_TOKEN, **payload}, timeout=3)
        if r.status_code != 200 or r.text.strip().lower() != "ok":
            print("Blynk update error:", r.status_code, r.text[:200])
        else:
            _last_blynk_send = now_ts
    except Exception as e:
        print("Blynk exception:", e)

# ---- Main ----
try:
    with serial.Serial(SERIAL_PORT, BAUD, timeout=TIMEOUT) as ser:
        print("Listening on", SERIAL_PORT)
        while _running:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            try:
                if line.startswith("{") and line.endswith("}"):
                    d = json.loads(line)
                    lux   = read_lux()
                    temp  = d.get("temp_c")
                    tds   = d.get("tds_ppm")
                    water = d.get("water")
                    print(f"JSON Temp={temp} TDS={tds} Water={water} Lux={lux}")
                    insert(temp, tds, water, lux, line)
                    blynk_update(temp=temp, tds=tds, water=water, lux=lux)
                    apply_led(lux)

                elif line.lower().startswith("water:"):
                    water = int(line.split(":", 1)[1])
                    print(f"TEXT Water={water}")
                    insert(water=water, raw=line)
                    blynk_update(water=water)

                else:
                    print("RAW", line)
                    insert(raw=line)

            except Exception as e:
                print("Parse/handle error:", e)
finally:
    try:
        led.off()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
    print("Closed DB & LED off. Bye.")
