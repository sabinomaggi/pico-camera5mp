import board
import time
import supervisor
import sys
import os
import rtc
from Arducam import Arducam, OV5642_2592x1944, OV5642_1600x1200

# Initialize RTC (useful for filenames if set)
r = rtc.RTC()

# Ensure images directory exists
try:
    os.mkdir("/images")
except OSError:
    pass # Already exists

# Initialize Camera
cam = Arducam()
cam.init_cam()
# Set to 5MP by default
cam.set_jpeg_size(OV5642_2592x1944)

print("CircuitPython Capture Ready!")
print("Images will be saved to the /images/ folder on the Pico.")

def save_image():
    print("ACK CMD Capture Started...")
    cam.clear_fifo_flag()
    cam.start_capture()
    
    start = time.monotonic()
    while not (cam.spi_read_reg(0x41) & 0x08):
        if time.monotonic() - start > 5:
            print("Capture Timeout!")
            return
        time.sleep(0.1)
        
    length = cam.get_fifo_length()
    if length == 0 or length >= 0x7FFFFF:
        print("Bad image size!")
        return

    # Generate filename: img_YYYYMMDD-HHMMSS.jpg
    t = r.datetime
    filename = f"/images/img_{t.tm_year:04d}{t.tm_mon:02d}{t.tm_mday:02d}-{t.tm_hour:02d}{t.tm_min:02d}{t.tm_sec:02d}.jpg"
    
    print(f"Saving to {filename} ({length} bytes)...")
    
    try:
        # Proactive read pointer reset
        cam.spi_write_reg(0x04, 0x10) 
        
        with open(filename, "wb") as f:
            chunk_size = 4096
            remaining = length
            while remaining > 0:
                to_read = min(remaining, chunk_size)
                data = cam.read_fifo_burst(to_read)
                f.write(data)
                remaining -= to_read
        
        print("Capture Saved Successfully!")
        # Also stream a success marker for the host if needed
        print("ACK IMG END")
    except Exception as e:
        print(f"Error saving file: {e}")
        print("NOTE: Did you install boot.py to enable write access?")
    
    cam.clear_fifo_flag()

# Main Loop
while True:
    if supervisor.runtime.serial_bytes_available:
        cmd = sys.stdin.read(1)
        if cmd == "\x10": # Trigger capture
            save_image()
        elif cmd == "\x11": # Re-init
            print("Re-initializing Camera...")
            cam.init_cam()
            cam.set_jpeg_size(OV5642_2592x1944)
            print("Re-init Done.")
    time.sleep(0.01)
