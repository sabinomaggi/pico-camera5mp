# Arducam 5MP Plus Capture for Raspberry Pi Pico 2

This project provides a robust solution for capturing high-resolution JPEG images (up to 5MP) from an **Arducam Mini 5MP Plus (B0068)** module using a **Raspberry Pi Pico 2** (RP2350) or **Raspberry Pi Pico** (RP2040).

Two platform options are available:
- **Arduino** (`main` branch): C++ firmware with a Python host script.
- **CircuitPython** (`dev` branch): Pure Python driver running natively on the Pico, with a separate Python host script.

## Features
- **Full 5MP Support**: Captured images at resolutions up to 2592x1944.
- **Hardware Stabilization**: Fixed timing and signal integrity issues present in official Arducam libraries when used with RP2040/RP2350.
- **Silent/Debug Modes**: All diagnostic output is controlled by a `DEBUG` flag (`False` by default). When `DEBUG = False`, the capture script runs silently — no prompts, no verbose output.
- **Auto-Port Detection**: The host script automatically finds the Pico's serial port on macOS (no manual configuration needed).
- **Automated Single-Shot Capture**: By default, the script connects, takes one picture, saves it, and exits.
- **Clean Naming**: Automatic timestamped filenames (`img_YYYYMMDD-HHMMSS.jpg`).

## Hardware Setup

### Connection Pinout
| Camera Signal | Pico Pin (GP) | Function |
| ------------- | ------------- | -------- |
| **CS**        | GP5           | Chip Select (SPI) |
| **MOSI**      | GP3           | Data In |
| **MISO**      | GP4           | Data Out |
| **SCK**       | GP2           | Clock |
| **GND**       | GND           | Ground |
| **VCC**       | 3V3           | Power (3.3V) |
| **SDA**       | GP8           | I2C Data |
| **SCL**       | GP9           | I2C Clock |

> [!NOTE]
> For a visual wiring diagram, refer to the official [Uctronics Connection Manual](https://www.uctronics.com/download/Amazon/B0067-B0068-Pico.pdf).

## Technical Implementation & Fixes
The primary objective of this project was to bridge the gap in the official Arducam drivers, which lacks native support for the Raspberry Pi Pico's RP2040/RP2350 architecture, even when using the Arduino IDE.

### Key Changes vs. Official Drivers:
1.  **VSYNC Polarity Hardlocking**: Fixed a common issue where the sensor's VSYNC pulses were missed by forcing active-low polarity in Register 0x03.
2.  **SPI Transaction Integrity**: Implemented `SPI.beginTransaction()` and `SPI.endTransaction()` within the critical data paths to prevent signal corruption during high-speed FIFO retrieval.
3.  **Explicit Pin Mapping**: Replaced default library assumptions with explicit RP2040 pin assignments (`Wire.setSDA/SCL`, `SPI.setRX/TX/SCK`).
4.  **Macro Collision Fixes**: Resolved naming conflicts (e.g., `CS` macro) that prevented the library from compiling on the Pico 2W.
5.  **FIFO Readout Optimization**: Enhanced the readout loop with proactive pointer resets to eliminate the "8-byte corruption" or "zero-byte data" issues common in early Pico-Arducam implementations.

## Getting Started

### 1. Arduino Firmware
1.  Open [pico_ov5642/pico_ov5642.ino](pico_ov5642/pico_ov5642.ino) in the Arduino IDE.
2.  Install the **Raspberry Pi Pico/RP2040** board support package.
3.  Upload the sketch to your Pico.

### 2. Changing Resolution
To change the capture resolution, simply modify the `SELECTED_RESOLUTION` variable at the top of [pico_ov5642/pico_ov5642.ino](pico_ov5642/pico_ov5642.ino):

```cpp
// Example: Switch to UXGA (1600x1200)
const int SELECTED_RESOLUTION = OV5642_1600x1200;

// Example: Switch to 5MP (2592x1944)
const int SELECTED_RESOLUTION = OV5642_2592x1944;
```

Supported constants include:
- `OV5642_320x240` (QVGA)
- `OV5642_640x480` (VGA)
- `OV5642_1024x768` (XGA)
- `OV5642_1600x1200` (UXGA)
- `OV5642_2592x1944` (5MP)

> [!IMPORTANT]
> Higher resolutions result in larger files and longer transfer times. For 5MP images, the transfer can take ~20-30 seconds at 115200 baud.

### 3. Python Capture Script
1.  Ensure you have `pyserial` installed:
    ```bash
    pip install pyserial
    ```
2.  Run the capture script:
    ```bash
    uv run pico_ov5642/capture.py
    ```
    Images are saved to the `images/` directory.

---

## CircuitPython (Alternative)
A native CircuitPython port is available on the `dev` branch. This version allows you to control the camera using high-level Python code on the device, without needing the Arduino IDE.

### 1. Install Clean CircuitPython
Install CircuitPython using the standard official build:
1.  Connect your Pico/Pico 2 to your computer in **BOOTSEL** mode.
2.  Open **Thonny IDE**.
3.  Go to **Tools** -> **Options** -> **Interpreter**.
4.  Select **CircuitPython (generic)** and click **Install or update CircuitPython**.
5.  Select your target board and the latest stable version. Click **Install**.

### 2. Deploy Driver
1.  Clone this repository and switch to the development branch: `git checkout dev`.
2.  Copy the following files from the `circuitpython/` directory to the `CIRCUITPY` drive:
    -   `Arducam.py`
    -   `OV5642_regs.py`
    -   `code.py`

### 3. Run Capture
The CircuitPython version **streams data to your Mac** via Serial. Run the dedicated host script:
```bash
uv run circuitpython/capture.py
```
The image will be saved to the `images/` folder on your computer.

> [!TIP]
> Set `DEBUG = True` at the top of both `code.py` (on the Pico) and `circuitpython/capture.py` (on the host) to enable verbose diagnostics, hex dumps, and the interactive capture menu.

## Project Structure

```
project12-pico-camera5mp/
├── pico_ov5642/              # Arduino platform
│   ├── ArduCAM.cpp / .h      # Arducam driver (C++)
│   ├── pico_ov5642.ino       # Arduino sketch
│   └── capture.py            # Host capture script (Arduino)
├── circuitpython/            # CircuitPython platform (dev branch)
│   ├── Arducam.py            # Arducam driver (Python)
│   ├── OV5642_regs.py        # Register definitions
│   ├── code.py               # Pico-side capture logic
│   └── capture.py            # Host capture script (CircuitPython)
└── images/                   # Captured images (shared)
```

## Attribution
This codebase was generated with the assistance of **Gemini** (Google) and **Claude Opus** (Anthropic), following the detailed supervision, technical insights, and continuous feedback provided by **Sabino Maggi**.

## Useful Links
- **Official Camera Page**: [Arducam 5MP Plus SPI Camera](https://www.arducam.com/arducam-5mp-plus-spi-cam-arduino-ov5642.html)
- **Official Documentation**: [Arducam 5MP Plus Manual](https://www.uctronics.com/download/Amazon/B0067-B0068-Pico.pdf)
