import time
import gc
import wifi
import terminalio
from adafruit_display_text import bitmap_label as label
from config.display_config import display, splash, main_group
from core.buttons import buttons
from core.wifi_setup import connect_wifi
from core.brightness import init_backlight, get_brightness, change_brightness, shutdown as shutdown_brightness
from core.web_server import init_server, poll, shutdown_server
from adafruit_debouncer import Debouncer

def draw_standby_screen():
    while main_group:
        main_group.pop()
    
    is_connected = wifi.radio.connected
    ip_addr = str(wifi.radio.ipv4_address) if is_connected else None
    
    hdr = label.Label(terminalio.FONT, text="SPRIG ASCII STREAMER", color=0x39FF14, x=4, y=10)
    main_group.append(hdr)
    
    if is_connected:
        lbl_ip = label.Label(terminalio.FONT, text=f"IP: http://{ip_addr}:80", color=0xFFFFFF, x=4, y=26)
        lbl_inst = label.Label(terminalio.FONT, text="Upload MP4 from phone", color=0x888888, x=4, y=42)
    else:
        lbl_ip = label.Label(terminalio.FONT, text="WiFi: Disconnected", color=0xFF5555, x=4, y=26)
        lbl_inst = label.Label(terminalio.FONT, text="Press J to connect WiFi", color=0x888888, x=4, y=42)
        
    main_group.append(lbl_ip)
    main_group.append(lbl_inst)
    
    status_text = "Status: Standby..." if is_connected else "Status: Offline Mode"
    lbl_stat = label.Label(terminalio.FONT, text=status_text, color=0x888888, x=4, y=58)
    main_group.append(lbl_stat)
    
    lbl_bright = label.Label(terminalio.FONT, text=f"Brightness: {get_brightness()}%", color=0x39FF14, x=4, y=74)
    main_group.append(lbl_bright)
    
    lbl_exit = label.Label(terminalio.FONT, text="Press L to shutdown", color=0x888888, x=4, y=90)
    main_group.append(lbl_exit)
    
    lbl_git1 = label.Label(terminalio.FONT, text="github.com/ioNihal/", color=0x555555, x=4, y=106)
    lbl_git2 = label.Label(terminalio.FONT, text="sprig-video2ascii", color=0x555555, x=4, y=118)
    main_group.append(lbl_git1)
    main_group.append(lbl_git2)
    
    display.refresh()

def main():
    try:
        # 1. Initialize backlight PWM
        init_backlight()
        
        # 2. Connect to WiFi
        connect_wifi()
        
        # 3. Initialize HTTP Server
        init_server()
        
        # 4. Draw home screen
        draw_standby_screen()
        
        # Setup debouncers for standby controls
        db_I = Debouncer(buttons["I"])
        db_K = Debouncer(buttons["K"])
        db_J = Debouncer(buttons["J"])
        db_L = Debouncer(buttons["L"])
        
        last_brightness_update = get_brightness()
        
        print("[SYSTEM] Standby loop active.")
        
        while True:
            # Update debouncers (which polls the web server internally via buttons.py)
            db_I.update()
            db_K.update()
            db_L.update()
            
            # Check for standby physical brightness changes
            brightness_changed = False
            if db_I.fell:
                change_brightness(10)
                brightness_changed = True
            elif db_K.fell:
                change_brightness(-10)
                brightness_changed = True
                
            # Check for shutdown trigger
            if db_L.fell:
                print("[SYSTEM] Shutdown triggered via Button L.")
                break
                
            # If not connected to WiFi, allow manual retry with J button
            if not wifi.radio.connected:
                db_J.update()
                if db_J.fell:
                    connect_wifi()
                    init_server()
                    draw_standby_screen()
                    
            # If a video was finished playing, redraw standby screen
            from core import ascii_player
            if not ascii_player.is_playing and len(main_group) <= 1:
                # ascii_player clears main_group on finish, so len is 0 or 1
                draw_standby_screen()
                
            # Update standby screen if brightness changed remotely/physically
            current_b = get_brightness()
            if brightness_changed or current_b != last_brightness_update:
                last_brightness_update = current_b
                # Make sure we don't redraw over playing video
                if not ascii_player.is_playing:
                    draw_standby_screen()
                
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("[SYSTEM] Standby loop stopped by user interrupt.")
    finally:
        print("[SYSTEM] Performing graceful shutdown...")
        # Display shutdown message to user
        try:
            from core.wifi_setup import show_screen
            show_screen("SYSTEM SHUTDOWN", [
                "Safe to power off.",
                "",
                "Toggle On/Off to restart"
            ])
            time.sleep(2.0)
        except Exception:
            pass
            
        # 1. Shutdown server
        try:
            shutdown_server()
        except Exception as e:
            print("Error shutting down server:", e)
            
        # 2. Shutdown brightness PWM
        try:
            shutdown_brightness()
        except Exception as e:
            print("Error shutting down brightness:", e)
            
        # 3. Deinit buttons to free GP pins
        try:
            for name, btn in buttons.items():
                print(f"Deinitializing button {name}...")
                btn.deinit()
        except Exception as e:
            print("Error deinitializing buttons:", e)
            
        print("[SYSTEM] Shutdown complete.")

if __name__ == "__main__":
    main()
