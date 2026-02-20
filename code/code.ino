#include "ArduCAM.h"
#include "memorysaver.h"
#include <SPI.h>
#include <Wire.h>

// Debug mode: set to 1 to enable diagnostic prints and scans, 0 to disable
#define DEBUG_MODE 0

// Pin configuration for Pico 2W as specified by user
const int CS = 5;

// Arducam instance
ArduCAM myCAM(OV5642, CS);

void setup() {
  uint8_t temp;

  // Initialize Serial and wait long enough for USB/Python to catch up
  Serial.begin(115200);
  unsigned long start_serial = millis();
  delay(2000);
  while (!Serial && (millis() - start_serial < 5000))
    ;
  delay(500);
  Serial.println(F("\n\nACK CMD --- ArduCAM Boot Start --- END"));

  // Initialize I2C with specified pins
  Wire.setSDA(8);
  Wire.setSCL(9);
  Wire.begin();

  // Initialize SPI with specified pins
  SPI.setRX(4);
  SPI.setTX(3);
  SPI.setSCK(2);
  SPI.begin();

  // Reset the CPLD
  pinMode(CS, OUTPUT);
  digitalWrite(CS, HIGH);
  myCAM.write_reg(0x07, 0x80);
  delay(100);
  myCAM.write_reg(0x07, 0x00);
  delay(100);

  // --- Hardware Sensor Reset/Wake Sequence ---
  // Bit 0: Reset (1=Release), Bit 1: PWDN (0=Normal), Bit 2: PWREN (1=Enable)
  myCAM.write_reg(ARDUCHIP_GPIO, 0x00); // Reset + PWDN + PWROFF
  delay(50);
  myCAM.write_reg(ARDUCHIP_GPIO, 0x05); // Release Reset + PWREN ON
  delay(200);

  // Check SPI interface
  while (1) {
    myCAM.write_reg(ARDUCHIP_TEST1, 0x55);
    temp = myCAM.read_reg(ARDUCHIP_TEST1);
    if (temp != 0x55) {
      Serial.println(F("ACK CMD SPI interface Error! END"));
      delay(1000);
      continue;
    } else {
      Serial.println(F("ACK CMD SPI interface OK. END"));
      break;
    }
  }

  // Check CPLD Revision
  temp = myCAM.read_reg(0x40);
  Serial.print(F("ACK CMD CPLD Revision: 0x"));
  Serial.print(temp, HEX);
  Serial.println(F(" END"));

  // Check Camera Module
  uint8_t vid, pid;
  while (1) {
#if DEBUG_MODE
    myCAM.rdSensorReg16_8(OV5642_CHIPID_HIGH, &vid);
    myCAM.rdSensorReg16_8(OV5642_CHIPID_LOW, &pid);
#endif
    if ((vid != 0x56) || (pid != 0x42)) {
      Serial.println(F("ACK CMD Can't find OV5642 module! END"));
      delay(1000);
      continue;
    } else {
      Serial.println(F("ACK CMD OV5642 detected. END"));
      break;
    }
  }

  // Set JPEG format and initialize
  myCAM.set_format(JPEG);
  myCAM.InitCAM();
  myCAM.OV5642_set_JPEG_size(OV5642_2592x1944);
  myCAM.clear_fifo_flag();
  myCAM.write_reg(ARDUCHIP_FRAMES,
                  0x00); // 0x00 means 1 frame for some versions

  // --- NEW: VSYNC Polarity Adjustment ---
  // If VSYNC pulses are being missed/inverted, toggle Bit 1 of Register 0x03
  uint8_t tim = myCAM.read_reg(0x03);
  myCAM.write_reg(
      0x03, tim | 0x02); // Force VSYNC Low Active (often needed for OV5642)

  Serial.println(F("ACK CMD Camera Ready! END"));
}

void loop() {
#if DEBUG_MODE
  static unsigned long last_heartbeat = 0;
  if (millis() - last_heartbeat > 5000) {
    uint8_t rev = myCAM.read_reg(0x40);
    myCAM.write_reg(ARDUCHIP_TEST1, 0xAA);
    uint8_t test = myCAM.read_reg(ARDUCHIP_TEST1);

    Serial.print(F("ACK CMD Heartbeat - CPLD Rev: 0x"));
    Serial.print(rev, HEX);
    Serial.print(F(" Test: 0x"));
    Serial.print(test, HEX);
    Serial.println(F(" END"));
    last_heartbeat = millis();
  }
#endif

  if (Serial.available()) {
    uint8_t temp = Serial.read();
    if (temp == 0x10) { // Single capture command
      capture_and_stream();
    } else if (temp == 0x11) { // Manual Re-Init
      Serial.println(F("ACK CMD Re-initializing Camera... END"));
      myCAM.InitCAM();
      myCAM.OV5642_set_JPEG_size(OV5642_2592x1944);
      Serial.println(F("ACK CMD Re-init Done. END"));
    } else {
      Serial.print(F("ACK CMD Received unknown byte: 0x"));
      Serial.print(temp, HEX);
      Serial.println(F(" END"));
    }
  }
}

void capture_and_stream() {
  uint8_t temp = 0, temp_last = 0;
  uint32_t length = 0;
  bool is_header = false;

  Serial.println(F("ACK CMD Capture Started... END"));

  // --- Non-Destructive Wakeup ---
  myCAM.wrSensorReg16_8(0x3008, 0x00); // Ensure awake
  myCAM.wrSensorReg16_8(0x503D, 0x00); // Disable Test Pattern
  delay(10);

#if DEBUG_MODE
  // --- NEW DEBUG: I2C Stability Check ---
  uint8_t vid = 0, pid = 0;
  myCAM.rdSensorReg16_8(OV5642_CHIPID_HIGH, &vid);
  myCAM.rdSensorReg16_8(OV5642_CHIPID_LOW, &pid);
  Serial.print(F("ACK CMD Pre-Cap PID Check: 0x"));
  Serial.print(vid, HEX);
  Serial.print(pid, HEX);
  Serial.println(F(" END"));

  // --- NEW DEBUG: Sensor Power Mode Check ---
  uint8_t pwr_mode = 0;
  myCAM.rdSensorReg16_8(0x3008, &pwr_mode);
  Serial.print(F("ACK CMD Sensor Pwr (0x3008): 0x"));
  Serial.print(pwr_mode, HEX);
  Serial.println(F(" END"));

  // --- NEW DEBUG: Signal Snapshot (10 samples over 100ms) ---
  Serial.print(F("ACK CMD Signal Snap: "));
  for (int i = 0; i < 10; i++) {
    Serial.print(myCAM.read_reg(ARDUCHIP_TRIG), HEX);
    Serial.print(F(" "));
    delay(10);
  }
  Serial.println(F(" END"));

  // --- NEW DEBUG: Signal Scan (More samples) ---
  uint16_t vsync_count = 0;
  for (int i = 0; i < 10000; i++) {
    if (myCAM.read_reg(ARDUCHIP_TRIG) & 0x01)
      vsync_count++;
  }
  Serial.print(F("ACK CMD VSYNC Scan (10000 samples): "));
  Serial.print(vsync_count);
  Serial.println(F(" Highs END"));
#endif

  // 1. Reset FIFO and Start bit
  myCAM.write_reg(ARDUCHIP_FIFO, 0x01); // Set Clear bit
  delay(10);
  myCAM.write_reg(ARDUCHIP_FIFO, 0x00); // Release Clear bit
  delay(10);
  // Reset Read/Write Pointers (Plus models need this)
  myCAM.write_reg(ARDUCHIP_FIFO, 0x10); // Reset Read Pointer
  myCAM.write_reg(ARDUCHIP_FIFO, 0x20); // Reset Write Pointer
  delay(10);

  // 2. Clear any lingering done bit
  myCAM.clear_fifo_flag();

#if DEBUG_MODE
  // 3. Optional: Verify VSYNC is pulsing (Bit 0 of 0x41)
  uint8_t status = myCAM.read_reg(ARDUCHIP_TRIG);
  Serial.print(F("ACK CMD Pre-Capture Trig: 0x"));
  Serial.print(status, HEX);
  Serial.println(F(" END"));
#endif

  // 4. Trigger Capture
  myCAM.start_capture();

  unsigned long start_cap = millis();
  unsigned long last_status_update = 0;

  while (!myCAM.get_bit(ARDUCHIP_TRIG, CAP_DONE_MASK)) {
    if (millis() - start_cap > 5000) {
      Serial.println(F("ACK CMD ERROR: Capture Timeout END"));
      return;
    }

#if DEBUG_MODE
    if (millis() - last_status_update > 500) {
      Serial.print(F("ACK CMD Wait... Trig: 0x"));
      Serial.print(myCAM.read_reg(ARDUCHIP_TRIG), HEX);
      Serial.println(F(" END"));
      last_status_update = millis();
    }
#endif
  }
  Serial.println(F("ACK CMD Capture Done. END"));
  delay(50); // Small wait for CPLD logic to settle

  // 7. Read FIFO length
  length = myCAM.read_fifo_length();
  Serial.print(F("ACK CMD Length: "));
  Serial.print(length);
  Serial.println(F(" END"));

  if (length >= MAX_FIFO_SIZE || length == 0) {
    Serial.println(F("ACK CMD ERROR: Bad image size END"));
    myCAM.clear_fifo_flag();
    return;
  }

  // 8. SPI Readout (Ensure CS logic is clean)
  // Reset read pointer BEFORE SPI transaction starts
  myCAM.write_reg(ARDUCHIP_FIFO, 0x10);

  SPI.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
  myCAM.CS_LOW();
  myCAM.set_fifo_burst();

  // If data is all zeros or too small, show hex and abort
  if (length < 64) {
    Serial.print(F("ACK CMD Raw Hex: "));
    for (uint32_t i = 0; i < length; i++) {
      temp = SPI.transfer(0x00);
      Serial.print(temp, HEX);
      Serial.print(F(" "));
    }
    Serial.println(F(" END"));
    myCAM.CS_HIGH();
    SPI.endTransaction();
    myCAM.clear_fifo_flag();
    return;
  }

  // Header marker for Python script
  Serial.println(F("ACK IMG END"));

  while (length--) {
    temp_last = temp;
    temp = SPI.transfer(0x00);

    if (is_header) {
      Serial.write(temp);
    } else if ((temp == 0xD8) && (temp_last == 0xFF)) {
      is_header = true;
      Serial.write(temp_last);
      Serial.write(temp);
    }

    if ((temp == 0xD9) && (temp_last == 0xFF)) {
      break;
    }
  }

  myCAM.CS_HIGH();
  SPI.endTransaction();
  myCAM.clear_fifo_flag();
}
