import board
import time
import supervisor
import sys

# Ensure all previously used buses are released before starting
# This prevents "SPI Interface Error" or "Pin in use" on soft reboots
try:
    import displayio
    displayio.release_displays()
except ImportError:
    pass

import busio
# Force release of any dangling locks from displayio (standard soft-reboot fix)

from Arducam import Arducam, OV5642_2592x1944, OV5642_1600x1200, OV5642_QVGA_Preview1, OV5642_QVGA_Preview2

SELECTED_RESOLUTION = OV5642_2592x1944

# Initialize Camera
try:
    time.sleep(1) # Give camera time to power up fully
except KeyboardInterrupt:
    pass

try:
    cam = Arducam()
    
    # --- Exact Arduino translate of setup() ---
    # 1. Hardware Sensor Reset/Wake Sequence
    cam.spi_write_reg(0x06, 0x00) # Reset + PWDN + PWROFF
    time.sleep(0.05)
    cam.spi_write_reg(0x06, 0x05) # Release Reset + PWREN ON
    time.sleep(0.2)
    
    # 2. Check SPI
    retry = 0
    while True:
        cam.spi_write_reg(0x00, 0x55)
        temp = cam.spi_read_reg(0x00)
        if temp == 0x55:
            print("ACK CMD SPI interface OK. END")
            break
        retry += 1
        if retry > 5:
            print("ACK CMD SPI interface Error! END")
            raise RuntimeError("SPI interface Error!")
        time.sleep(0.5)
        
    # 3. Check CPLD Revision
    rev = cam.spi_read_reg(0x40)
    print(f"ACK CMD CPLD Revision: 0x{rev:02X} END")
    
    # 3b. Check Camera ID
    retry = 0
    while True:
        try:
            vid = cam.rdSensorReg16_8(0x300a)
            pid = cam.rdSensorReg16_8(0x300b)
            if vid == 0x56 and pid == 0x42:
                print("ACK CMD OV5642 detected. END")
                break
        except Exception:
            pass # Ignore I2C timeouts like [Errno 116] while sensor boots
            
        retry += 1
        if retry > 5:
            print("ACK CMD Can't find OV5642 module! END")
            raise RuntimeError("OV5642 sensor unresponsive")
        time.sleep(0.5)
    
    # 4. Init format and size
    cam._write_regs(OV5642_QVGA_Preview1)
    cam._write_regs(OV5642_QVGA_Preview2)
    time.sleep(0.1)
    
    cam.set_jpeg_size(SELECTED_RESOLUTION)
    cam.clear_fifo_flag()
    cam.spi_write_reg(0x01, 0x00) # 1 frame
    
    # VSYNC Polarity Adjustment (CRITICAL)
    tim = cam.spi_read_reg(0x03)
    cam.spi_write_reg(0x03, tim | 0x02)
    print("ACK CMD Camera Ready! END")
    
except Exception as e:
    print(f"Error initializing camera: {e}")
    print("Re-plug the USB to hard reset!")
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            pass

print("CircuitPython Capture Ready!")

def stream_image():
    # Signal start of capture to host
    print("ACK CMD Capture Started... END")
    
    # --- Non-Destructive Wakeup (MATCH ARDUINO) ---
    cam.wrSensorReg16_8(0x3008, 0x00) # Ensure awake
    cam.wrSensorReg16_8(0x503D, 0x00) # Disable Test Pattern
    time.sleep(0.01)
    
    # --- NEW DEBUG: VSYNC Scan ---
    vsync_count = 0
    for _ in range(1000):
        if cam.spi_read_reg(0x41) & 0x01:
            vsync_count += 1
    print(f"ACK CMD VSYNC Scan (1000 samples): {vsync_count} Highs END")
    
    # 1. Reset FIFO and Start bit (MATCH ARDUINO EXACTLY)
    cam.spi_write_reg(0x04, 0x01) # Set Clear bit
    time.sleep(0.01)
    cam.spi_write_reg(0x04, 0x00) # Release Clear bit
    time.sleep(0.01)
    cam.spi_write_reg(0x04, 0x10) # Reset Read Pointer
    cam.spi_write_reg(0x04, 0x20) # Reset Write Pointer
    time.sleep(0.01)
    
    cam.clear_fifo_flag()
    cam.start_capture()
    
    start = time.monotonic()
    last_status = 0
    while not (cam.spi_read_reg(0x41) & 0x08):
        if time.monotonic() - start > 5:
            print("ACK CMD ERROR: Capture Timeout END")
            return
        if time.monotonic() - last_status > 0.5:
            last_status = time.monotonic()

    print("ACK CMD Capture Done. END")
    time.sleep(0.05) # Settle CPLD
        
    length = cam.get_fifo_length()
    print(f"ACK CMD Length: {length} END")
    
    if length == 0 or length >= 0x7FFFFF:
        print("ACK CMD ERROR: Bad image size END")
        cam.clear_fifo_flag()
        return

    # 8. SPI Readout (Match Arduino byte-by-byte search)
    cam.spi_write_reg(0x04, 0x10) # Reset read pointer BEFORE SPI transaction
    
    # Signal start of image data stream using raw bytes
    sys.stdout.buffer.write(b"ACK IMG END\n")
    sys.stdout.buffer.flush()
    
    # Burst command
    while not cam.spi.try_lock():
        pass
    cam.spi_cs.value = False
    cam.spi.write(bytes([0x3c]))
    
    is_header = False
    temp = 0
    temp_last = 0
    
    for _ in range(length):
        temp_last = temp
        result = bytearray(1)
        cam.spi.readinto(result)
        temp = result[0]
        
        if is_header:
            sys.stdout.buffer.write(bytes([temp]))
        elif temp == 0xD8 and temp_last == 0xFF:
            is_header = True
            sys.stdout.buffer.write(bytes([temp_last, temp]))
            
        if temp == 0xD9 and temp_last == 0xFF:
            break
            
    cam.spi_cs.value = True
    cam.spi.unlock()
    cam.clear_fifo_flag()
    
    sys.stdout.buffer.flush()

# Main Loop
print("CircuitPython Capture Ready! Waiting for 'CAPTURE' command...")

import supervisor

cmd_buffer = ""
while True:
    try:
        if supervisor.runtime.serial_bytes_available:
            cmd_buffer += sys.stdin.read(supervisor.runtime.serial_bytes_available)
            if "CAPTURE" in cmd_buffer:
                print("\n--- Interactive Triggering Capture ---")
                cmd_buffer = "" # Clear buffer
                stream_image()
            elif len(cmd_buffer) > 64:
                cmd_buffer = "" # Prevent memory overflow
        time.sleep(0.01)
    except KeyboardInterrupt:
        pass
