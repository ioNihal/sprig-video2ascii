import wifi
import os
import time
import terminalio
from adafruit_display_text import bitmap_label as label
from config.display_config import display, splash, main_group

def show_screen(title, lines):
    # Clear main group
    while main_group:
        main_group.pop()
        
    # Draw title
    title_lbl = label.Label(terminalio.FONT, text=title, color=0x39FF14, x=4, y=10)
    main_group.append(title_lbl)
    
    # Draw lines
    for i, line in enumerate(lines):
        line_lbl = label.Label(terminalio.FONT, text=line, color=0xFFFFFF, x=4, y=26 + i * 14)
        main_group.append(line_lbl)
        
    display.refresh()

def sleep_check_cancel(seconds, interval=0.1):
    try:
        from core.buttons import buttons
        t_end = time.monotonic() + seconds
        while time.monotonic() < t_end:
            # W button is active low
            if not buttons["W"]._io.value:
                return True
            time.sleep(interval)
    except Exception as e:
        print("[WIFI] Cancel check error:", e)
        time.sleep(seconds)
    return False

def connect_wifi():
    try:
        from core.buttons import buttons
    except Exception as e:
        print("[WIFI] Buttons not loaded yet:", e)
        buttons = {}

    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
    
    if not ssid or ssid == "Your_WiFi_SSID":
        show_screen("WI-FI SETUP", [
            "No SSID found!",
            "Set CIRCUITPY_WIFI_SSID",
            "in settings.toml",
            "",
            "Press W to skip"
        ])
        while True:
            if "W" in buttons and not buttons["W"]._io.value:
                print("[WIFI] Setup skipped (no SSID).")
                return False
            time.sleep(0.1)
            
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        show_screen("WI-FI SETUP", [
            "Connecting to:",
            f"SSID: {ssid}",
            f"Attempt {attempt}/{max_retries}...",
            "",
            "Press W to skip"
        ])
        
        # Check cancel button right before trying
        if "W" in buttons and not buttons["W"]._io.value:
            print("[WIFI] Setup skipped by user.")
            return False
            
        try:
            wifi.radio.connect(ssid, password)
        except Exception as e:
            print(f"WiFi Connection Error (Attempt {attempt}):", e)
            
        if wifi.radio.connected:
            ip = str(wifi.radio.ipv4_address)
            show_screen("WI-FI CONNECTED", [
                f"SSID: {ssid}",
                f"IP: {ip}:80",
                "Dashboard open at:",
                f"http://{ip}:80/"
            ])
            time.sleep(2.0)
            return True
            
        if attempt < max_retries:
            show_screen("WI-FI FAILED", [
                f"SSID: {ssid}",
                "Failed to connect.",
                "Retrying in 3s...",
                "",
                "Press W to skip"
            ])
            if sleep_check_cancel(3.0):
                print("[WIFI] Setup cancelled by user.")
                return False
        else:
            show_screen("WI-FI FAILED", [
                f"SSID: {ssid}",
                "Failed to connect.",
                "Proceeding offline...",
                "Press W to continue"
            ])
            sleep_check_cancel(3.0)
            
    return False
