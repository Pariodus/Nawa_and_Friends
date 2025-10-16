#!/usr/bin/env python3
import serial
import sqlite3
import datetime
import signal
import sys
import os

# ===== Serial config =====
# Prefer the stable symlink; if you're sure about Pi 2/ttyAMA0, keep it.
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/serial0")  # or "/dev/ttyAMA0"
BAUD = 115200
TIMEOUT = 1

# ===== DB config =====
DB_PATH = "mqtt_messages.db"  # reuse the same DB
TOPIC = "rpi5/local/water"    # stays compatible with your messages schema

# ----- open DB and ensure schema -----
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("PRAGMA journal_mode=WAL;")
cur.execute("PRAGMA synchronous=NORMAL;")
cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    topic TEXT,
    payload TEXT
);
""")
conn.commit()

# graceful shutdown
_running = True
def _shutdown(signum, frame):
    global _running
    print("\nStopping...", flush=True)
    _running = False

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

# ----- open Serial -----
ser = serial.Serial(SERIAL_PORT, BAUD, timeout=TIMEOUT)
print(f"Listening from ESP32 on {SERIAL_PORT} @ {BAUD} → logging to {DB_PATH}")

# ----- main loop -----
try:
    while _running:
        raw = ser.readline()
        if not raw:
            continue
        try:
            line = raw.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            print("Decode error:", e)
            continue

        if not line.startswith("Water:"):
            continue

        try:
            water_val = int(line.split(":", 1)[1].strip())
        except Exception as e:
            print("Parse error:", line, "|", e)
            continue

        ts = datetime.datetime.now().isoformat(timespec="seconds")
        payload = str(water_val)

        # insert row
        cur.execute(
            "INSERT INTO messages (timestamp, topic, payload) VALUES (?, ?, ?)",
            (ts, TOPIC, payload)
        )
        conn.commit()

        print(f"[{ts}] {TOPIC} | {payload}", flush=True)
finally:
    try:
        ser.close()
    except Exception:
        pass
    conn.close()
    print("Closed serial and SQLite. Bye.")
