import board
import digitalio
import time

_web_server = None

class VirtualButton:
    def __init__(self, pin):
        self._io = digitalio.DigitalInOut(pin)
        self._io.switch_to_input(pull=digitalio.Pull.UP)
        self.virtual_press_time = 0.0  # Timestamp of when virtual press started

    @property
    def value(self):
        global _web_server
        # Poll web server locally to avoid circular import issues
        if _web_server is None:
            try:
                from core import web_server
                _web_server = web_server
            except Exception:
                pass
        
        if _web_server is not None and _web_server.server_active:
            try:
                _web_server.poll()
            except Exception:
                pass
            
        # Return physical state first (active low)
        if not self._io.value:
            return False
            
        # Hold virtual press for 250ms so Debouncer registers it correctly
        if time.monotonic() - self.virtual_press_time < 0.250:
            return False
            
        return True

    def trigger_virtual_press(self):
        self.virtual_press_time = time.monotonic()

    def deinit(self):
        try:
            self._io.deinit()
        except Exception:
            pass

from config.buttons_config import btn_pins

buttons = {}
for k, p in btn_pins.items():
    buttons[k] = VirtualButton(p)

