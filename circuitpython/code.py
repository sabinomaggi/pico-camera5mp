import board
import time
import supervisor
import sys
from Arducam import Arducam, OV5642_2592x1944, OV5642_1600x1200

# Initialize Camera
cam = Arducam()
cam.init_cam()
# Set to 5MP by default
cam.set_jpeg_size(OV5642_2592x1944)

print("CircuitPython Capture Ready!")

def stream_image():
    print("ACK CMD Capture Started... END")
    cam.clear_fifo_flag()
    cam.start_capture()
    
    start = time.monotonic()
    while not (cam.spi_read_reg(0x41) & 0x08):
        if time.monotonic() - start > 5:
            print("ACK CMD ERROR: Capture Timeout END")
            return
        time.sleep(0.1)
        
    length = cam.get_fifo_length()
    print(f"ACK CMD Length: {length} END")
    
    if length == 0 or length >= 0x7FFFFF:
        print("ACK CMD ERROR: Bad image size END")
        return

    # Signal start of image stream
    # sys.stdout.write is better for binary-like control in some environments
    # but we can use print for the header.
    print("ACK IMG END")
    
    # Read and stream in chunks to avoid memory issues on Pico
    chunk_size = 4096
    remaining = length
    
    # Proactive read pointer reset (FIX FROM ARDUINO)
    cam.spi_write_reg(0x04, 0x10) 
    
    while remaining > 0:
        to_read = min(remaining, chunk_size)
        data = cam.read_fifo_burst(to_read)
        sys.stdout.buffer.write(data)
        remaining -= to_read
    
    sys.stdout.buffer.flush()
    cam.clear_fifo_flag()

# Main Loop
while True:
    if supervisor.runtime.serial_bytes_available:
        cmd = sys.stdin.read(1)
        if cmd == "\x10": # Trigger capture
            stream_image()
        elif cmd == "\x11": # Re-init
            print("ACK CMD Re-initializing Camera... END")
            cam.init_cam()
            cam.set_jpeg_size(OV5642_2592x1944)
            print("ACK CMD Re-init Done. END")
    time.sleep(0.01)
