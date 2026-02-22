import board
import busio
import time as utime
import digitalio
from OV5642_regs import (
    OV5642_QVGA_Preview, 
    OV5642_JPEG_Capture_QSXGA, 
    ov5642_2592x1944, 
    ov5642_320x240
)

# Constants
OV5642 = 0x01
ARDUCHIP_FIFO = 0x04
ARDUCHIP_TRIG = 0x41
CAP_DONE_MASK = 0x08
ARDUCHIP_GPIO = 0x06 

class Arducam(object):
    def __init__(self, cs_pin=board.GP5, sda_pin=board.GP8, scl_pin=board.GP9, 
                 sck_pin=board.GP2, mosi_pin=board.GP3, miso_pin=board.GP4):
        self.I2cAddress = 0x3c
        
        self.spi_cs = digitalio.DigitalInOut(cs_pin)
        self.spi_cs.direction = digitalio.Direction.OUTPUT
        self.spi_cs.value = True
        
        # SPI Bus (2MHz Safety)
        self.spi = busio.SPI(clock=sck_pin, MOSI=mosi_pin, MISO=miso_pin)
        while not self.spi.try_lock(): pass
        self.spi.configure(baudrate=2000000, polarity=0, phase=0, bits=8)
        self.spi.unlock()
        
        # Direct I2C
        self.i2c = busio.I2C(scl=scl_pin, sda=sda_pin, frequency=100000)
        
        # Reset CPLD
        self.spi_write_reg(0x07, 0x80)
        utime.sleep(0.1)
        self.spi_write_reg(0x07, 0x00)
        utime.sleep(0.1)

    def spi_write_reg(self, address, value):
        while not self.spi.try_lock(): pass
        self.spi.configure(baudrate=2000000)
        self.spi_cs.value = False
        self.spi.write(bytes([address | 0x80, value]))
        self.spi_cs.value = True
        self.spi.unlock()

    def spi_read_reg(self, address):
        while not self.spi.try_lock(): pass
        self.spi.configure(baudrate=2000000)
        self.spi_cs.value = False
        self.spi.write(bytes([address & 0x7F]))
        result = bytearray(1)
        self.spi.readinto(result)
        self.spi_cs.value = True
        self.spi.unlock()
        return result[0]

    def wrSensorReg16_8(self, addr, val):
        while not self.i2c.try_lock(): pass
        try:
            self.i2c.writeto(self.I2cAddress, bytes([(addr >> 8) & 0xFF, addr & 0xFF, val]))
        finally:
            self.i2c.unlock()
        utime.sleep(0.001)

    def rdSensorReg16_8(self, addr):
        while not self.i2c.try_lock(): pass
        try:
            self.i2c.writeto(self.I2cAddress, bytes([(addr >> 8) & 0xFF, addr & 0xFF]))
            result = bytearray(1)
            self.i2c.readfrom_into(self.I2cAddress, result)
            return result[0]
        finally:
            self.i2c.unlock()

    def init_cam(self):
        self.spi_write_reg(ARDUCHIP_GPIO, 0x00)
        utime.sleep(0.05)
        self.spi_write_reg(ARDUCHIP_GPIO, 0x05)
        utime.sleep(0.2)

        while True:
            self.spi_write_reg(0x00, 0x55)
            if self.spi_read_reg(0x00) == 0x55:
                print("SPI Interface OK")
                break
            print("SPI Interface Error!")
            utime.sleep(1)

        while True:
            vid = self.rdSensorReg16_8(0x300a)
            pid = self.rdSensorReg16_8(0x300b)
            if vid == 0x56 and pid == 0x42:
                print("OV5642 detected")
                break
            print(f"Can't find OV5642 module! (VID: 0x{vid:02x}, PID: 0x{pid:02x})")
            utime.sleep(1)

        self.wrSensorReg16_8(0x3008, 0x80)
        utime.sleep(0.1)
        self._write_regs(OV5642_QVGA_Preview)
        utime.sleep(0.1)
        self._write_regs(OV5642_JPEG_Capture_QSXGA)
        utime.sleep(0.1)
        self._write_regs(ov5642_320x240)
        utime.sleep(0.1)
        
        self.wrSensorReg16_8(0x3103, 0x93)
        self.wrSensorReg16_8(0x3818, 0xa8)
        self.wrSensorReg16_8(0x3621, 0x10)
        self.wrSensorReg16_8(0x3801, 0xb0)
        self.wrSensorReg16_8(0x4407, 0x08)
        self.wrSensorReg16_8(0x5888, 0x00)
        self.wrSensorReg16_8(0x5000, 0xFF)
        
        self.spi_write_reg(0x01, 0x00)
        tim = self.spi_read_reg(0x03)
        self.spi_write_reg(0x03, tim | 0x02) # VSYNC Active Low
        
        self.wrSensorReg16_8(0x3008, 0x00)
        utime.sleep(0.1)

    def _write_regs(self, regs):
        for i in range(0, len(regs), 3):
            addr_h = regs[i]
            addr_l = regs[i+1]
            val = regs[i+2]
            addr = (addr_h << 8) | addr_l
            if addr == 0xffff: 
                utime.sleep(0.005)
                continue
            self.wrSensorReg16_8(addr, val)

    def set_jpeg_size(self, size_regs):
        self._write_regs(size_regs)
        utime.sleep(0.1)

    def reset_fifo(self):
        self.spi_write_reg(ARDUCHIP_FIFO, 0x01)
        utime.sleep(0.005)
        self.spi_write_reg(ARDUCHIP_FIFO, 0x00)
        utime.sleep(0.005)

    def start_capture(self):
        self.spi_write_reg(ARDUCHIP_FIFO, 0x01)
        self.spi_write_reg(ARDUCHIP_FIFO, 0x02)

    def get_fifo_length(self):
        l1 = self.spi_read_reg(0x42)
        l2 = self.spi_read_reg(0x43)
        l3 = self.spi_read_reg(0x44) & 0x7f
        return (l3 << 16) | (l2 << 8) | l1

    def read_fifo_burst(self, length):
        # Reset Read Pointer OUTSIDE the lock to avoid deadlock with spi_write_reg
        self.spi_write_reg(ARDUCHIP_FIFO, 0x10)
        
        while not self.spi.try_lock(): pass
        self.spi.configure(baudrate=2000000)
        
        cmd_buf = bytearray(length + 1)
        res_buf = bytearray(length + 1)
        cmd_buf[0] = 0x3c
        
        self.spi_cs.value = False
        self.spi.write_readinto(cmd_buf, res_buf)
        self.spi_cs.value = True
        self.spi.unlock()
        
        return res_buf[1:]
