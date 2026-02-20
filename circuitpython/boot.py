import storage
import board
import digitalio

# To allow the Pico to save images to its own flash, we need to make the 
# filesystem writable by the code. 
# WARNING: This makes the CIRCUTPY drive READ-ONLY from your computer.
# To revert: Connect GP0 to GND or delete this file via another method.

switch = digitalio.DigitalInOut(board.GP0)
switch.direction = digitalio.Direction.INPUT
switch.pull = digitalio.Pull.UP

# If GP0 is NOT connected to GND, the code can write to the flash.
# If GP0 is connected to GND, the computer can write (safe mode).
if switch.value:
    storage.remount("/", False)
else:
    storage.remount("/", True)
