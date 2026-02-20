import board
import busio
import time as utime
import digitalio
from OV5642_regs import *

# Constants
OV5642 = 0x01
MAX_FIFO_SIZE = 0x7FFFFF
ARDUCHIP_FIFO = 0x04
ARDUCHIP_TRIG = 0x41
CAP_DONE_MASK = 0x08
ARDUCHIP_FRAMES = 0x01
ARDUCHIP_GPIO = 0x06 # GPIO register for power/reset

class Arducam(object):
    def __init__(self, cs_pin=board.GP5, sda_pin=board.GP8, scl_pin=board.GP9, 
                 sck_pin=board.GP2, mosi_pin=board.GP3, miso_pin=board.GP4):
        self.I2cAddress = 0x3c
        
        # CS Pin
        self.spi_cs = digitalio.DigitalInOut(cs_pin)
        self.spi_cs.direction = digitalio.Direction.OUTPUT
        self.spi_cs.value = True
        
        # SPI Bus
        self.spi = busio.SPI(clock=sck_pin, MOSI=mosi_pin, MISO=miso_pin)
        while not self.spi.try_lock():
            pass
        self.spi.configure(baudrate=4000000, polarity=0, phase=0, bits=8)
        self.spi.unlock()
        
        # I2C Bus (use software I2C if hardware pins conflict, but we use board pins)
        self.i2c = busio.I2C(scl=scl_pin, sda=sda_pin, frequency=100000)
        
        # Reset CPLD
        self.spi_write_reg(0x07, 0x80)
        utime.sleep(0.1)
        self.spi_write_reg(0x07, 0x00)
        utime.sleep(0.1)

    def spi_write_reg(self, address, value):
        while not self.spi.try_lock():
            pass
        self.spi_cs.value = False
        self.spi.write(bytes([address | 0x80, value]))
        self.spi_cs.value = True
        self.spi.unlock()

    def spi_read_reg(self, address):
        while not self.spi.try_lock():
            pass
        self.spi_cs.value = False
        self.spi.write(bytes([address & 0x7F]))
        result = bytearray(1)
        self.spi.readinto(result)
        self.spi_cs.value = True
        self.spi.unlock()
        return result[0]

    def wrSensorReg16_8(self, addr, val):
        while not self.i2c.try_lock():
            pass
        try:
            self.i2c.writeto(self.I2cAddress, bytes([(addr >> 8) & 0xFF, addr & 0xFF, val]))
        finally:
            self.i2c.unlock()
        utime.sleep(0.001)

    def rdSensorReg16_8(self, addr):
        while not self.i2c.try_lock():
            pass
        try:
            # Step 1: Write the 16-bit address we want to read from
            self.i2c.writeto(self.I2cAddress, bytes([(addr >> 8) & 0xFF, addr & 0xFF]))
            
            # Step 2: Read the 8-bit response
            result = bytearray(1)
            self.i2c.readfrom_into(self.I2cAddress, result)
            return result[0]
        finally:
            self.i2c.unlock()

    def init_cam(self):
        # 1. Hardware Wakeup Sequence (ARDUCHIP_GPIO)
        self.spi_write_reg(ARDUCHIP_GPIO, 0x00) # Reset + PWDN + PWROFF
        utime.sleep(0.05)
        self.spi_write_reg(ARDUCHIP_GPIO, 0x05) # Release Reset + PWREN ON
        utime.sleep(0.2)

        # 2. Check SPI
        while True:
            self.spi_write_reg(0x00, 0x55)
            if self.spi_read_reg(0x00) == 0x55:
                print("SPI Interface OK")
                break
            print("SPI Interface Error!")
            utime.sleep(1)

        # 3. Check Camera ID
        while True:
            vid = self.rdSensorReg16_8(0x300a)
            pid = self.rdSensorReg16_8(0x300b)
            if vid == 0x56 and pid == 0x42:
                print("OV5642 detected")
                break
            print(f"Can't find OV5642 module! (VID: 0x{vid:02x}, PID: 0x{pid:02x})")
            utime.sleep(1)

        # 4. Initialize Sensor
        self.wrSensorReg16_8(0x3008, 0x80) # Reset sensor
        utime.sleep(0.1)
        self._write_regs(OV5642_QVGA_Preview1)
        self._write_regs(OV5642_QVGA_Preview2)
        utime.sleep(0.1)
        
        # 5. VSYNC Polarity Fix (ACTIVE LOW) - CRITICAL FIX FROM ARDUINO
        tim = self.spi_read_reg(0x03)
        self.spi_write_reg(0x03, tim | 0x02)
        
        self.clear_fifo_flag()
        print("Camera Ready!")

    def _write_regs(self, regs):
        for addr, val in regs:
            if addr == 0xffff: break
            self.wrSensorReg16_8(addr, val)

    def set_jpeg_size(self, size_regs):
        self._write_regs(OV5642_JPEG_Capture_QSXGA)
        self._write_regs(size_regs)
        utime.sleep(0.1)
        self.wrSensorReg16_8(0x3818, 0xa8)
        self.wrSensorReg16_8(0x3621, 0x10)
        self.wrSensorReg16_8(0x3801, 0xb0)
        self.wrSensorReg16_8(0x4407, 0x04)

    def clear_fifo_flag(self):
        self.spi_write_reg(ARDUCHIP_FIFO, 0x01)

    def start_capture(self):
        # Reset pointers
        self.spi_write_reg(ARDUCHIP_FIFO, 0x10)
        self.spi_write_reg(ARDUCHIP_FIFO, 0x20)
        # Trigger
        self.spi_write_reg(ARDUCHIP_FIFO, 0x02)

    def get_fifo_length(self):
        l1 = self.spi_read_reg(0x42)
        l2 = self.spi_read_reg(0x43)
        l3 = self.spi_read_reg(0x44) & 0x7f
        return (l3 << 16) | (l2 << 8) | l1

    def read_fifo_burst(self, length):
        while not self.spi.try_lock():
            pass
        self.spi_cs.value = False
        
        # Burst command
        self.spi.write(bytes([0x3c]))
        
        # Read the data block
        data = bytearray(length)
        self.spi.readinto(data)
        
        self.spi_cs.value = True
        self.spi.unlock()
        return data
