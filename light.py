#!/usr/bin/env python3
import time
from smbus2 import SMBus

# ที่อยู่อุปกรณ์ (0x23 = ADDR ลอย, 0x5C = ADDR ต่อ VCC)
ADDR = 0x23
BUS = 1

# คำสั่ง BH1750
POWER_ON   = 0x01
RESET      = 0x07
# โหมดอ่านต่อเนื่อง ความละเอียดสูง 1 lx/0.5lx (กำลังดีและไว้นิ่ง)
CONT_HRES  = 0x10  # 1 lx resolution, 120ms typical

def read_lux(bus, addr=ADDR):
    # เปิดเครื่องและรีเซ็ต
    bus.write_byte(addr, POWER_ON)
    bus.write_byte(addr, RESET)
    # ตั้งโหมดอ่านต่อเนื่องแบบ High-Resolution
    bus.write_byte(addr, CONT_HRES)
    # รอเวลาคอนเวอร์ท (ตาม datasheet ~120ms, กันเหนียว 180ms)
    time.sleep(0.18)
    # อ่าน 2 ไบต์ (MSB, LSB)
    data = bus.read_i2c_block_data(addr, 0x00, 2)
    raw = (data[0] << 8) | data[1]
    # แปลงเป็นลักซ์ (ค่า/1.2 ตามสเปค)
    lux = raw / 1.2
    return lux

if __name__ == "__main__":
    with SMBus(BUS) as bus:
        while True:
            try:
                lux = read_lux(bus, ADDR)
                print(f"BH1750 Lux: {lux:.2f}")
            except OSError as e:
                print("I2C error:", e)
            time.sleep(1)
