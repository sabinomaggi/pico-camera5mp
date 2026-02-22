import board
import time
import supervisor
import sys
import usb_cdc
import busio

# Ensure all previously used buses are released
print("--- Pico Booting ---")
try:
    import displayio
    displayio.release_displays()
except ImportError:
    pass

from Arducam import Arducam
from OV5642_regs import (
    OV5642_QVGA_Preview, 
    OV5642_JPEG_Capture_QSXGA, 
    ov5642_2592x1944, 
    ov5642_320x240
)

SELECTED_RESOLUTION = ov5642_2592x1944
LOCKED_MODAL_BITS = 0x02 
DEBUG = False # Set to True for verbose hex dumps and parity diagnostics 

# Initialize Camera
print("ACK CMD Booting System... END")
sys.stdout.write("\n")

def check_for_header(data):
    for i in range(len(data)-1):
        b1, b2 = data[i], data[i+1]
        # 1. Standard
        if b1 == 0xFF and b2 == 0xD8: return f"Standard at {i}", i
        # 2. Bit-Reversed
        if b1 == 0xFF and b2 == 0x1B: return f"Bit-Reversed at {i}", i
        # 3. Bit-Inverted
        if b1 == 0x00 and b2 == 0x27: return f"Bit-Inverted at {i}", i
        # 4. Swapped Nibbles
        if b1 == 0xFF and b2 == 0x8D: return f"Nibble-Swap at {i}", i
        # 5. Shifted Right 1-bit
        if b1 == 0x7F and b2 == 0xEC: return f"Shift-R1 at {i}", i
        # 6. Shifted Left 1-bit
        if b1 == 0xFF and b2 == 0xB0: return f"Shift-L1 at {i}", i
    return None, -1

def sync_hardware():
    global LOCKED_MODAL_BITS
    print("ACK CMD Syncing Hardware (Safe-Sweep 16)... END")
    tim_base = cam.spi_read_reg(0x03) & ~0x0F
    
    for m in range(16):
        if DEBUG: sys.stdout.write(f"ACK CMD Mode 0x{m:02X}: Testing... END\n")
        cam.spi_write_reg(0x03, tim_base | m)
        time.sleep(0.01)
        
        cam.reset_fifo()
        cam.start_capture()
        
        # Wait for capture
        start = time.monotonic()
        done = False
        while time.monotonic() - start < 1.0:
            if cam.spi_read_reg(0x41) & 0x08:
                done = True
                break
            
        if not done:
            sys.stdout.write(f"ACK CMD Mode 0x{m:02X}: No VSYNC END\n")
            continue
            
        length = cam.get_fifo_length()
        if length > 1000:
            data = cam.read_fifo_burst(min(1024, length))
            if DEBUG:
                hex_head = " ".join([f"{b:02X}" for b in data[:16]])
                sys.stdout.write(f"ACK CMD Mode 0x{m:02X}: Len={length}, Start=[{hex_head}] END\n")
            
            label, idx = check_for_header(data)
            if label:
                if DEBUG: sys.stdout.write(f"ACK CMD VSYNC: Locked Mode 0x{m:02X} ({label}) END\n")
                LOCKED_MODAL_BITS = m
                return True
        cam.reset_fifo()
        
    sys.stdout.write("ACK CMD VSYNC: Sync Failed. No Header Found. END\n")
    return False

def run_diagnostics():
    print("\n--- Hardware Diagnostics ---")
    try:
        print("ACK CMD Starting Initializer... END")
        cam.init_cam()
        print("ACK CMD Sensor Initialized. END")
        
        rev = cam.spi_read_reg(0x40)
        print(f"ACK CMD CPLD Revision: 0x{rev:02X} END")
        
        vid = cam.rdSensorReg16_8(0x300a)
        pid = cam.rdSensorReg16_8(0x300b)
        print(f"ACK CMD ID: VID=0x{vid:02x}, PID=0x{pid:02x} END")
            
        cam.set_jpeg_size(SELECTED_RESOLUTION)
        time.sleep(0.5)
        
        sync_hardware()
        print("ACK CMD Camera Ready! END")
        return True
        
    except Exception as e:
        print(f"ACK CMD Error: {e} END")
        return False

def stream_image():
    global LOCKED_MODAL_BITS
    print("ACK CMD Capture Started... END")
    
    tim_base = cam.spi_read_reg(0x03) & ~0x0F
    cam.spi_write_reg(0x03, tim_base | LOCKED_MODAL_BITS)

    cam.reset_fifo()
    cam.start_capture()
    
    start = time.monotonic()
    while not (cam.spi_read_reg(0x41) & 0x08):
        if time.monotonic() - start > 5:
            print("ACK CMD ERROR: Timeout END")
            return

    print("ACK CMD Capture Done. END")
    time.sleep(0.01)
        
    length = cam.get_fifo_length()
    print(f"ACK CMD Length: {length} END")
    
    if length < 1000:
        print("ACK CMD ERROR: Bad Size END")
        cam.reset_fifo()
        return

    # Header Check
    header_check = cam.read_fifo_burst(min(2048, length))
    label, soi_index = check_for_header(header_check)
            
    if soi_index == -1:
        if DEBUG:
            hex_head = " ".join([f"{b:02X}" for b in header_check[:48]])
            print(f"ACK CMD ERROR: No Header (Start: {hex_head}) END")
        else:
            print("ACK CMD ERROR: No valid JPEG Start of Image (SOI) found END")
        cam.reset_fifo()
        return

    print(f"ACK CMD Header found: {label} END")
    time.sleep(0.05) # Settle before stream signal

    # Binary Stream
    usb_cdc.console.write(b"ACK IMG END\n")
    time.sleep(0.05) # Settle before RAW data
    
    # Reset Read Pointer (0x04 is ARDUCHIP_FIFO)
    cam.spi_write_reg(0x04, 0x10) 
    
    while not cam.spi.try_lock(): pass
    cam.spi.configure(baudrate=2000000)
    
    cam.spi_cs.value = False
    cam.spi.write(bytes([0x3c])) # Burst Command

    
    if soi_index > 0:
        skip_buf = bytearray(soi_index)
        cam.spi.readinto(skip_buf)

    CHUNK_SIZE = 4096
    buf = bytearray(CHUNK_SIZE)
    remaining = length - soi_index
    
    while remaining > 0:
        to_read = min(CHUNK_SIZE, remaining)
        if to_read < CHUNK_SIZE: buf = bytearray(to_read)
        cam.spi.readinto(buf)
        usb_cdc.console.write(buf)
        remaining -= to_read
            
    cam.spi_cs.value = True
    cam.spi.unlock()
    cam.reset_fifo()
    print("ACK CMD Stream Finished. END")

# Main
try:
    time.sleep(1) 
    cam = Arducam()
    run_diagnostics()
except Exception as e:
    print(f"ACK CMD Fatal: {e} END")

last_heartbeat = time.monotonic()
print("\nCircuitPython Waiting for command...")

while True:
    if supervisor.runtime.serial_bytes_available:
        raw_cmd = sys.stdin.read(supervisor.runtime.serial_bytes_available)
        if "\x10" in raw_cmd:
            stream_image()
        if "\x11" in raw_cmd:
            run_diagnostics()
        if "STOP" in raw_cmd.upper():
            sys.exit(0)
            
    if time.monotonic() - last_heartbeat > 5.0:
        print("ACK CMD Heartbeat... END")
        last_heartbeat = time.monotonic()
    time.sleep(0.01)
