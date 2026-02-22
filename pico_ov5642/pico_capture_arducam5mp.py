import serial
import serial.tools.list_ports
import time
import os
import datetime
import sys

# --- Configuration ---
PORT = None # Set to None for Auto-Detection
BAUD = 115200
IMAGE_DIR = "images"
DEBUG = False

if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

def find_pico_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = p.description.lower()
        # Common identifiers for Pico / CircuitPython on Mac
        if "pico" in desc or "circuitpython" in desc or "usbmodem" in desc:
            return p.device
    return None

def connect_pico():
    global PORT
    target_port = PORT or find_pico_port()
    
    if not target_port:
        print("Error: Could not find Pico serial port. Is it plugged in?")
        return None
        
    print(f"Connecting to Pico on {target_port}...")
    try:
        ser = serial.Serial(target_port, BAUD, timeout=1)
        return ser
    except Exception as e:
        print(f"Error connecting to {target_port}: {e}")
        return None

def main():
    ser = connect_pico()
    if not ser: return

    print(f"Waiting for Pico to signal 'Camera Ready'...")
    ser.reset_input_buffer()
    
    ready = False
    start_time = time.time()
    ser.timeout = 5
    
    while not ready:
        line = ser.readline()
        if not line:
            if time.time() - start_time > 15:
                print("Poking Pico (0x11)...")
                ser.write(b'\x11')
                start_time = time.time()
            continue
            
        try:
            text = line.decode('utf-8', errors='ignore').strip()
            if text:
                if DEBUG and any(x in text for x in ["ACK CMD", "Pico Status"]):
                    print(f"Pico: {text}")
            
            if any(x in text for x in ["Camera Ready!", "Waiting for command"]):
                ready = True
        except:
            pass
    
    ser.timeout = 1

    while True:
        print("\n" + "="*40)
        user_input = input("Press [Enter] to capture, 's' for status, 'q' to quit: ").lower()
        
        if user_input == 'q':
            break
        elif user_input == 's':
            ser.write(b'\x11')
            continue

        # Trigger
        print("Triggering capture (Byte 0x10)...")
        ser.reset_input_buffer() # Clear any heartbeats
        ser.write(b'\x10')
        ser.flush()
        
        ser.timeout = 10 
        print("Waiting for Pico to process image...")
        
        # 1. Wait for ACK IMG END signal while printing Pico output
        signal_buf = bytearray()
        while True:
            char = ser.read(1)
            if not char: break
            signal_buf.extend(char)
            if b"ACK IMG END\n" in signal_buf:
                break
        
        # Print all the "ACK CMD" status messages that were hidden (only if DEBUG is true)
        text = signal_buf.decode('utf-8', errors='ignore')
        if DEBUG:
            for line in text.strip().split("\n"):
                if "ACK CMD" in line:
                    print(f"Pico: {line.strip()}")
        
        if b"ACK IMG END" not in signal_buf:
            print(f"Error: Timed out waiting for image signal. Got: {text[:200]}")
            continue
            
        print("Receiving JPEG bitstream...")
        img_bytes = bytearray()
        found_start = False
        transfer_start = time.time()
        
        # 2. Bulk Transfer Loop
        while time.time() - transfer_start < 20: # 20s timeout for 5MP
            # Read in large chunks for speed
            chunk = ser.read(16384) 
            if not chunk:
                if found_start: break # End of stream
                continue
            
            img_bytes.extend(chunk)
            
            if not found_start:
                # Seek for SOI in the accumulated data
                soi_idx = img_bytes.find(b'\xff\xd8')
                if soi_idx != -1:
                    print(f"JPEG Header found at byte {soi_idx}!")
                    img_bytes = img_bytes[soi_idx:]
                    found_start = True
            
            if found_start:
                if DEBUG: print(f"Buffered {len(img_bytes)//1024} KB...")
                if b'\xff\xd9' in chunk:
                    eoi_idx = img_bytes.find(b'\xff\xd9')
                    if eoi_idx != -1:
                        img_bytes = img_bytes[:eoi_idx+2]
                        print("End of Image (EOI) detected.")
                        break
        
        ser.timeout = 1

        if len(img_bytes) > 20000: # 5MP JPEG should be > 20KB for a scene
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"img_{timestamp}.jpg"
            filepath = os.path.join(IMAGE_DIR, filename)
            
            with open(filepath, 'wb') as f:
                f.write(img_bytes)
            
            print(f"\nSUCCESS")
            print(f"Filename: {filename}")
            print(f"File size: {len(img_bytes)} bytes")
            print(f"Location: {filepath}")
        else:
            if found_start:
                print(f"Error: Received only {len(img_bytes)} bytes. Image likely truncated.")
            else:
                hex_head = " ".join([f"{b:02X}" for b in img_bytes[:32]])
                print(f"Error: No JPEG header found in {len(img_bytes)} bytes received. (Start: {hex_head})")

    ser.close()

if __name__ == "__main__":
    main()
