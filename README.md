# sprig-video2ascii

A standalone, highly optimized **CircuitPython** project that lets you wirelessly convert and stream any MP4 video from your phone/computer to be played back as an ASCII loop on the Sprig console's TFT display.

Featuring a streamlined codebase, zero background telemetry overhead, hardware-level physical breakout triggers, and a modern cyberpunk dashboard served directly from the Sprig (powered by Raspberry Pi Pico 2 W).

---

## 🚀 Key Features

*   **Wireless Cyberpunk Dashboard**: Serves a sleek, dark cyberpunk matrix mobile-friendly dashboard over Wi-Fi.
*   **In-Browser Real-Time Canvas Conversion**: Upload any MP4 video on your phone; the dashboard converts it to ASCII frames on the fly using HTML5 canvas, provides a live preview, and streams the frames directly to the Pico's memory.
*   **Smooth 20 FPS Playback**: Optimized single-core cooperative execution ensures the SPI display writes (20 FPS / 50ms per frame) remain smooth and stutter-free.
*   **Backlight Brightness Control**: Adjust the display backlight dimming dynamically (10% - 100%) via high-frequency PWM on **GP17** (both from the web dashboard and physical buttons).
*   **Low-Level Hardware Hard Stop**: Pressing the physical **W** button (GP5) instantly breaks the playback rendering loop and returns the device to the standby screen, clearing memory.
*   **Clean & Modular Pin Configurations**: All physical pin mappings (display, buttons, speaker, LEDs) are isolated in the `config/` directory for simple hardware modifications.

---

## 🔌 Hardware Pin Mapping

Based on the official Sprig console schematic:

### ST7735 TFT LCD Display Connections:
*   `GP18` → SPI SCK (Clock)
*   `GP19` → SPI MOSI (Data)
*   `GP20` → CS (Chip Select)
*   `GP22` → D/C (Data/Command)
*   `GP26` → RESET
*   `GP17` → LITE (Backlight PWM Pin)

### Console Buttons (Active Low):
*   `GP5`  → Button **W** (Hard Stop Video / Exit)
*   `GP12` → Button **I** (Brightness Up)
*   `GP14` → Button **K** (Brightness Down)
*   `GP6`  → Button **A** (Unused)
*   `GP7`  → Button **S** (Unused)
*   `GP8`  → Button **D** (Unused)
*   `GP13` → Button **J** (Unused)
*   `GP15` → Button **L** (Gracefull shutdown)

### MAX98357A I2S Audio Speaker:
*   `GP10` → BCLK (Bit Clock)
*   `GP11` → LRCLK (Word Select)
*   `GP9`  → DIN (Data Input)

### Status LEDs:
*   `GP4`  → `LED_R` (Red Right LED)
*   `GP28` → `LED_L` (Green Left LED)

---

## 📁 Repository Structure

```
sprig-video2ascii/
├── main.py                 # Standby bootloader / Entry point
├── settings.toml           # Wi-Fi SSID and Password configuration
├── config/                 # Hardware Pin configurations
│   ├── display_config.py   # SPI display & standard backlight definitions
│   ├── buttons_config.py   # Console switch mapping
│   ├── speaker_config.py   # MAX98357A I2S audio pin mapping
│   └── led_config.py       # Status LED pin mapping
├── core/                   # Application engine files
│   ├── brightness.py       # PWM duty-cycle dimming module
│   ├── buttons.py          # Input wrappers and web polling hook
│   ├── wifi_setup.py       # Wi-Fi network initialization handler
│   ├── ascii_player.py     # Fast 20 FPS video rendering & raw stop loop
│   └── web_server.py       # Dashboard web server & API router
└── lib/                    # Essential compiled CircuitPython libraries
    ├── adafruit_st7735r.mpy
    ├── adafruit_display_text/
    ├── adafruit_debouncer.mpy
    └── adafruit_ticks.mpy
```

---

## ⚙️ Installation & Usage

1.  **Prepare CircuitPython**: Ensure your Raspberry Pi Pico 2 WH is running **CircuitPython 9.x**.
2.  **Configure Wi-Fi**: Edit the `settings.toml` file in the root folder with your Wi-Fi name and password:
    ```toml
    CIRCUITPY_WIFI_SSID = "Your SSID"
    CIRCUITPY_WIFI_PASSWORD = "Your Password"
    ```
3.  **Copy Files**: Copy the entire contents of this repository to your Sprig's flash drive (`CIRCUITPY/`).
4.  **Open Dashboard**: Once the Sprig connects, its display will print the local IP address (e.g., `http://192.168.1.100:80/`). Open this URL on your phone or computer.
5.  **Select & Stream**: Choose an MP4 video (up to 15 seconds) from the dashboard, click **Stream to Sprig**, and watch the ASCII loop play immediately!

---

## 👤 Author

*   **Nihal K**
    *   GitHub: [@ioNihal](https://github.com/ioNihal)
    *   Portfolio: [ionihal.vercel.app](https://ionihal.vercel.app)
    *   Repository: [sprig-video2ascii](https://github.com/ioNihal/sprig-video2ascii)

