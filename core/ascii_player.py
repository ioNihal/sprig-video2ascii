import time
import gc
import terminalio
from adafruit_display_text import bitmap_label as label
from config.display_config import display, splash, main_group
from core.buttons import buttons

cached_animation_data = None
cached_frame_count = 0
is_playing = False

def clear_ascii_cache():
    global cached_animation_data, cached_frame_count
    cached_animation_data = None
    cached_frame_count = 0
    gc.collect()

def set_cached_animation(text):
    global cached_animation_data, cached_frame_count
    clear_ascii_cache()
    if not text:
        return True
    try:
        cached_animation_data = text.encode("utf-8")
        cached_frame_count = len(cached_animation_data) // 324
        gc.collect()
        return True
    except (MemoryError, Exception) as e:
        print("[WIFI] ASCII cache error:", e)
        clear_ascii_cache()
        return False

def receive_and_cache_ascii(conn, body_start_bytes, content_length):
    global cached_animation_data, cached_frame_count
    clear_ascii_cache()
    gc.collect()
    
    if content_length == 0:
        return True
        
    try:
        # Pre-allocate bytearray to avoid fragmentation
        data = bytearray(content_length)
        
        # Copy already read bytes
        if isinstance(body_start_bytes, str):
            body_start_bytes = body_start_bytes.encode("utf-8")
            
        start_len = len(body_start_bytes)
        data[0:start_len] = body_start_bytes
        
        # Stream remaining bytes directly from socket
        bytes_read = start_len
        conn.settimeout(5.0)
        
        while bytes_read < content_length:
            mv = memoryview(data)[bytes_read:]
            n = conn.recv_into(mv)
            if n == 0:
                break
            bytes_read += n
            
        if bytes_read != content_length:
            raise ValueError("Incomplete data: {} of {}".format(bytes_read, content_length))
            
        cached_frame_count = content_length // 324
        if cached_frame_count == 0:
            raise ValueError("No complete frames")
            
        cached_animation_data = data
        gc.collect()
        print("[WIFI] Streamed ASCII Caching complete. Frames:", cached_frame_count)
        return True
    except (MemoryError, Exception) as e:
        print("[WIFI] Streamed ASCII cache error:", e)
        clear_ascii_cache()
        return False

def play_loop_standalone():
    global cached_animation_data, cached_frame_count, is_playing
    
    if not cached_animation_data or cached_frame_count == 0:
        return
        
    is_playing = True
    old_auto_refresh = display.auto_refresh
    display.auto_refresh = False
    
    try:
        while main_group:
            main_group.pop()
            
        # Setup text display label using ultra-fast bitmap_label
        lbl = label.Label(terminalio.FONT, text="", color=0x39FF14, x=2, y=8, line_spacing=1.0)
        main_group.append(lbl)
        
        if main_group not in splash:
            splash.append(main_group)
        display.refresh()
        
        frame_idx = 0
        frame_time = 1.0 / 20.0  # 50ms per frame (20 FPS)
        frame_len = 324
        
        last_brightness_time = 0.0
        
        # Import web_server dynamically to avoid circular dependencies
        from core import web_server
        
        while True:
            t0 = time.monotonic()
            
            # 1. Check physical Hard Stop button (W / GP5) raw value instantly (no web server poll)
            if not buttons["W"]._io.value:
                print("[SYSTEM] Hard stop button pressed!")
                break
                
            # 2. Check physical brightness buttons (I / GP12 and K / GP14) with debouncing
            now = time.monotonic()
            if now - last_brightness_time > 0.2:
                if not buttons["I"]._io.value:
                    from core.brightness import change_brightness
                    change_brightness(10)
                    last_brightness_time = now
                    print("[SYSTEM] Brightness manually increased.")
                elif not buttons["K"]._io.value:
                    from core.brightness import change_brightness
                    change_brightness(-10)
                    last_brightness_time = now
                    print("[SYSTEM] Brightness manually decreased.")
            
            # 3. Poll web server (limited to once every 500ms inside web_server.poll)
            if web_server.server_active:
                try:
                    web_server.poll()
                except Exception as e:
                    print("Web server poll error during playback:", e)
                    
            # 4. Check if someone stopped playback from web dashboard
            if not is_playing:
                break
                
            # 5. Decode frame on-the-fly and display
            start = frame_idx * frame_len
            end = start + frame_len
            frame_str = cached_animation_data[start:end].decode("utf-8")
            lbl.text = frame_str
            display.refresh()
            
            frame_idx = (frame_idx + 1) % cached_frame_count
            
            # Clean up memory occasionally
            if frame_idx % 15 == 0:
                gc.collect()
            
            # Frame delay
            while time.monotonic() - t0 < frame_time:
                # Fast direct check for Stop button to exit loop immediately
                if not buttons["W"]._io.value:
                    print("[SYSTEM] Hard stop button pressed during frame delay!")
                    return
                time.sleep(0.002)
                
    except KeyboardInterrupt:
        pass
    finally:
        is_playing = False
        display.auto_refresh = old_auto_refresh
        gc.collect()
        # Clear splash to prepare for home screen
        while main_group:
            main_group.pop()
        display.refresh()
