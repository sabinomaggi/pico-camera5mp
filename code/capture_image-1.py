import serial
import time
import os
import datetime

# CONFIGURATION
# Update this port to match your Pico's serial port on macOS
# Typically something like '/dev/cu.usbmodemXXXX'
SERIAL_PORT = '/dev/cu.usbmodem22401'  # Updated to user's actual port
BAUD_RATE = 115200
TIMEOUT = 5  # Serial timeout in seconds
# GLOBAL SETTINGS
DEBUG = False  # Set to True to see all Pico diagnostic logs

# Directory configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'images'))

def capture_image():
    # Ensure images directory exists
    if not os.path.exists(IMAGE_DIR):
        print(f"Creating directory: {IMAGE_DIR}")
        os.makedirs(IMAGE_DIR)

    try:
        print(f"Connecting to Pico on {SERIAL_PORT}...")
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        
        # Wait for Pico to initialize
        wait_time = 15 if DEBUG else 5
        print(f"Waiting {wait_time}s for Pico to initialize...")
        start_time = time.time()
        while time.time() - start_time < wait_time:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if DEBUG and line:
                    print(f"Pico Boot: {line}")
            time.sleep(0.1)

        ser.reset_input_buffer()

        # Optional: Send 0x11 to Re-Init if we missed the boot logs
        # This command (0x11) can be used to re-initialize the camera
        # and get fresh diagnostic output if needed.
        # ser.write(b'\x11')
        # time.sleep(2) # Give Pico time to process re-init

        print("Triggering single capture (0x10)...")
        ser.write(b'\x10')

        # Wait for "ACK IMG END" header
        print("Waiting for image stream...")
        start_time = time.time()
        found_header = False
        
        while time.time() - start_time < 10:
            line = ser.readline()
            if line:
                try:
                    text = line.decode('ascii', errors='ignore').strip()
                    if DEBUG and text: print(f"Pico: {text}")
                    if "ACK IMG END" in text:
                        found_header = True
                        break
                    if "ACK CMD ERROR" in text:
                        print(f"Pico reported error: {text}")
                        return
                    if DEBUG and "ACK CMD Length:" in text:
                        # Extract length just for info
                        try:
                            l = int(text.split(":")[1].split(" ")[1])
                            print(f"Pico reports FIFO length: {l} bytes")
                        except: pass
                except:
                    pass
        
        if not found_header:
            print("Error: Did not receive 'ACK IMG END' from Pico.")
            return

        print("Receiving JPEG data... (searching for FF D8)")
        img_bytes = bytearray()
        last_byte = b''
        bytes_received = 0
        
        # Long timeout for 5MP image transfer
        transfer_start = time.time()
        while time.time() - transfer_start < 60:
            byte = ser.read(1)
            if not byte:
                continue
            
            img_bytes.append(byte[0])
            bytes_received += 1
            
            if bytes_received % 10240 == 0:
                print(f"Received {bytes_received // 1024} KB...")

            # Detect JPEG End Of Image (FF D9)
            if last_byte == b'\xff' and byte == b'\xd9':
                print(f"End of Image (EOI) detected after {bytes_received} bytes.")
                break
            last_byte = byte

        if len(img_bytes) > 1000:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"img_{timestamp}.jpg"
            filepath = os.path.join(IMAGE_DIR, filename)
            
            with open(filepath, 'wb') as f:
                f.write(img_bytes)
            
            print(f"Success! Image saved to: {filepath}")
            print(f"File size: {len(img_bytes)} bytes")
        else:
            print(f"Error: Received only {len(img_bytes)} bytes. Image likely corrupt.")

    except Exception as e:
        print(f"Fatal Error: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    capture_image()
