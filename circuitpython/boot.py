import usb_cdc

# Enable both the standard console (REPL) and a dedicated data port
usb_cdc.enable(console=True, data=True)
