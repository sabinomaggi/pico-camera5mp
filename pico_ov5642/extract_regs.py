import re
import os

HEADER_PATH = "/Volumes/Data SSD/Development/Antigravity/project12-pico-camera5mp/pico_ov5642/ov5642_regs.h"
OUTPUT_PATH = "/Volumes/Data SSD/Development/Antigravity/project12-pico-camera5mp/circuitpython/OV5642_regs.py"

def extract_array(content, array_name):
    # Find start of array
    start_match = re.search(fr"const struct sensor_reg {array_name}\[\] PROGMEM =\s*{{", content)
    if not start_match:
        return None
    
    start_idx = start_match.end()
    # Find end of array (matching braces)
    brace_count = 1
    end_idx = start_idx
    while brace_count > 0 and end_idx < len(content):
        if content[end_idx] == '{':
            brace_count += 1
        elif content[end_idx] == '}':
            brace_count -= 1
        end_idx += 1
    
    array_content = content[start_idx:end_idx-1]
    
    # Extract {addr, val} pairs
    pairs = re.findall(r"\{\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*\}", array_content)
    
    return [(int(addr, 16), int(val, 16)) for addr, val in pairs]

def to_bytes_string(pairs):
    if not pairs:
        return "b''"
    
    lines = []
    current_line = []
    for addr, val in pairs:
        current_line.append(f"\\x{(addr >> 8) & 0xFF:02x}\\x{addr & 0xFF:02x}\\x{val & 0xFF:02x}")
        if len(current_line) >= 20:
            lines.append("b'" + "".join(current_line) + "'")
            current_line = []
    
    if current_line:
        lines.append("b'" + "".join(current_line) + "'")
    
    return "(\n    " + "\n    ".join(lines) + "\n)"

with open(HEADER_PATH, 'r') as f:
    content = f.read()

qvga_preview = extract_array(content, "OV5642_QVGA_Preview")
jpeg_qsxga = extract_array(content, "OV5642_JPEG_Capture_QSXGA")
res_2592x1944 = extract_array(content, "ov5642_2592x1944")
res_320x240 = extract_array(content, "ov5642_320x240")
res_1600x1200 = extract_array(content, "ov5642_1600x1200")

# Format output
with open(OUTPUT_PATH, 'w') as f:
    f.write("# Optimized OV5642 Registers (Bytes format)\n")
    f.write("# Each register is 3 bytes: [AddrHigh, AddrLow, Value]\n")
    f.write("# Marker 0xFFFF, 0xFF is used for end of list\n\n")
    
    f.write(f"OV5642_QVGA_Preview = {to_bytes_string(qvga_preview)}\n\n")
    f.write(f"OV5642_JPEG_Capture_QSXGA = {to_bytes_string(jpeg_qsxga)}\n\n")
    f.write(f"ov5642_2592x1944 = {to_bytes_string(res_2592x1944)}\n\n")
    f.write(f"ov5642_320x240 = {to_bytes_string(res_320x240)}\n\n")
    f.write(f"OV5642_1600x1200 = {to_bytes_string(res_1600x1200)}\n\n")

print("Successfully extracted and formatted registers.")
