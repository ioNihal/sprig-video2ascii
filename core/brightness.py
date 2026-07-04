import board
import pwmio
from config.display_config import bl

_backlight = None
_current_brightness = 50  # Default to 50%

def init_backlight():
    global _backlight
    try:
        # Release the digital pin configured in display_config
        bl.deinit()
    except Exception:
        pass
    
    try:
        _backlight = pwmio.PWMOut(
            board.GP17,
            frequency=5000,
            duty_cycle=int(_current_brightness * 65535 / 100)
        )
    except Exception as e:
        print("Failed to initialize PWM backlight:", e)

def change_brightness(delta: int) -> None:
    global _current_brightness, _backlight
    _current_brightness = max(10, min(100, _current_brightness + delta))
    if _backlight is not None:
        try:
            _backlight.duty_cycle = int(_current_brightness * 65535 / 100)
        except Exception as e:
            print("Failed to set duty cycle:", e)

def set_brightness(val: int) -> None:
    global _current_brightness, _backlight
    _current_brightness = max(10, min(100, val))
    if _backlight is not None:
        try:
            _backlight.duty_cycle = int(_current_brightness * 65535 / 100)
        except Exception as e:
            print("Failed to set duty cycle:", e)

def get_brightness() -> int:
    return _current_brightness

def shutdown() -> None:
    global _backlight
    if _backlight is not None:
        try:
            _backlight.deinit()
        except Exception:
            pass
