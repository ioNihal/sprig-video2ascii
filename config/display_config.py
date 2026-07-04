import board
import busio
import digitalio
import displayio
from adafruit_st7735r import ST7735R
from fourwire import FourWire

displayio.release_displays()

# Display setup
spi = busio.SPI(clock=board.GP18, MOSI=board.GP19)
tft_cs = board.GP20
tft_dc = board.GP22
tft_rst = board.GP26

display_bus = FourWire(spi, command=tft_dc, chip_select=tft_cs, reset=tft_rst)
display = ST7735R(display_bus, width=160, height=128, rotation=270, bgr=True, color_depth=16)

# Backlight control
bl = digitalio.DigitalInOut(board.GP17)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# Layer management
splash = displayio.Group()
display.root_group = splash

# Create layer groups
main_group = displayio.Group()
splash.append(main_group)