import time
import wifi
import gc
import microcontroller

try:
    import socketpool
    WIFI_AVAILABLE = True
except ImportError:
    WIFI_AVAILABLE = False

server_socket = None
pool = None
last_poll_time = 0
last_init_time = 0
server_active = False

def init_server():
    global server_socket, pool, last_init_time, server_active
    if not WIFI_AVAILABLE or not wifi.radio.connected:
        return False
        
    now = time.monotonic()
    if now - last_init_time < 10.0:
        return False
    last_init_time = now
        
    try:
        if server_socket is not None:
            server_active = True
            return True
            
        pool = socketpool.SocketPool(wifi.radio)
        server_socket = pool.socket()
        try:
            sol_socket = getattr(pool, "SOL_SOCKET", 1)
            so_reuseaddr = getattr(pool, "SO_REUSEADDR", 4)
            server_socket.setsockopt(sol_socket, so_reuseaddr, 1)
        except Exception as se:
            print("[WIFI] setsockopt failed:", se)
            
        server_socket.settimeout(0.0)
        server_socket.bind(("0.0.0.0", 80))
        server_socket.listen(2)
        server_active = True
        print("[WIFI] Standalone ASCII dashboard running at http://{}:80".format(wifi.radio.ipv4_address))
        return True
    except Exception as e:
        print("[WIFI] Server bind error:", e)
        server_socket = None
        server_active = False
        return False

def shutdown_server():
    global server_socket, server_active
    server_active = False
    if server_socket is not None:
        try:
            server_socket.close()
        except Exception:
            pass
        server_socket = None
        print("[WIFI] Web Server stopped.")

def poll():
    global server_socket, last_poll_time, server_active
    if not server_active:
        return
        
    now = time.monotonic()
    
    # Check if currently playing video
    from core import ascii_player
    is_playing = getattr(ascii_player, "is_playing", False)
    
    # 500ms delay during playback to prevent frame stutters, 50ms otherwise
    limit = 0.500 if is_playing else 0.050
    if now - last_poll_time < limit:
        return
    last_poll_time = now
    
    if not wifi.radio.connected:
        if server_socket is not None:
            shutdown_server()
        return
        
    if server_socket is None:
        init_server()
        if server_socket is None:
            return
            
    try:
        conn, addr = server_socket.accept()
    except OSError as e:
        # Non-blocking OS error checks (EAGAIN, EWOULDBLOCK, ETIMEDOUT)
        if e.errno in (11, 115, 116) or "timed out" in str(e).lower():
            return
        print("[WIFI] Accept error, restarting server:", e)
        shutdown_server()
        return
        
    try:
        conn.settimeout(0.2)
        buf = bytearray(1024)
        nbytes = conn.recv_into(buf)
        req = buf[:nbytes].decode("utf-8", "ignore")
        
        path = ""
        method = ""
        body_start = ""
        
        if req.startswith("GET "):
            method = "GET"
            start_idx = 4
            end_idx = req.find(" HTTP/1.1", start_idx)
            if end_idx != -1:
                path = req[start_idx:end_idx]
        elif req.startswith("POST "):
            method = "POST"
            start_idx = 5
            end_idx = req.find(" HTTP/1.1", start_idx)
            if end_idx != -1:
                path = req[start_idx:end_idx]
                
        if method == "POST":
            content_length = 0
            cl_idx = req.lower().find("content-length:")
            if cl_idx != -1:
                cl_start = cl_idx + len("content-length:")
                cl_end = req.find("\r", cl_start)
                if cl_end == -1:
                    cl_end = req.find("\n", cl_start)
                if cl_end != -1:
                    try:
                        content_length = int(req[cl_start:cl_end].strip())
                    except ValueError:
                        pass
                        
            hdr_end = req.find("\r\n\r\n")
            if hdr_end == -1:
                hdr_end = req.find("\n\n")
                header_sep = "\n\n"
            else:
                header_sep = "\r\n\r\n"
                
            if hdr_end != -1:
                body_start = req[hdr_end + len(header_sep):]
                
            # Max 125 KB payload guard
            if content_length > 125000:
                print("[WIFI] Payload too large:", content_length)
                conn.send(b"HTTP/1.1 413 Payload Too Large\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                conn.close()
                return
                
        # Route handler
        if path == "/" or path == "/index.html" or path == "":
            serve_dashboard(conn)
        elif path == "/play_ascii" and method == "POST":
            try:
                gc.collect()
                success = ascii_player.receive_and_cache_ascii(conn, body_start, content_length)
                if success:
                    send_json_response(conn, {"status": "ok"})
                    if not ascii_player.is_playing:
                        try:
                            ascii_player.play_loop_standalone()
                        except Exception as e:
                            print("Error starting ascii loop:", e)
                else:
                    send_json_response(conn, {"status": "error", "message": "Pico out of memory."})
            except Exception as e:
                print("Error handling play_ascii:", e)
                try:
                    send_json_response(conn, {"status": "error", "message": str(e)})
                except Exception:
                    pass
        elif path.startswith("/brightness?val="):
            try:
                val = int(path.split("=")[1])
                from core import brightness
                brightness.set_brightness(val)
            except Exception as e:
                print("Remote brightness error:", e)
            send_json_response(conn, {"status": "ok"})
        elif path.startswith("/action?cmd="):
            cmd = path.split("=")[1]
            if cmd == "stop_video":
                print("[WIFI] Dashboard Stop Video request")
                ascii_player.is_playing = False
                send_json_response(conn, {"status": "stopping"})
            elif cmd == "reboot":
                send_json_response(conn, {"status": "rebooting"})
                conn.close()
                time.sleep(0.5)
                microcontroller.reset()
            else:
                send_json_response(conn, {"status": "ok"})
        else:
            conn.send(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            conn.close()
    except Exception as e:
        print("Web request error:", e)
        try:
            conn.close()
        except Exception:
            pass

def send_all(conn, data):
    try:
        if isinstance(data, str):
            data = data.encode("utf-8")
        bytes_sent = 0
        while bytes_sent < len(data):
            chunk = data[bytes_sent : bytes_sent + 512]
            sent = conn.send(chunk)
            if sent == 0:
                break
            bytes_sent += sent
    except Exception:
        pass

def send_json_response(conn, obj):
    import json
    body = json.dumps(obj)
    res = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}".format(len(body), body)
    send_all(conn, res)
    conn.close()

def serve_dashboard(conn):
    html = """HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sprig ASCII Streamer Dashboard</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
        
        body {
            font-family: 'Outfit', -apple-system, sans-serif;
            background: #121110;
            color: #E6E4DE;
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            overflow-x: hidden;
        }

        .header {
            margin-top: 40px;
            margin-bottom: 24px;
            text-align: center;
        }

        .header h1 {
            font-size: 32px;
            font-weight: 700;
            color: #E6E4DE;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin: 0 0 8px 0;
        }

        .header p {
            color: #969085;
            font-size: 14px;
            margin: 0;
        }

        .container {
            width: 90%;
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 24px;
            padding-bottom: 40px;
        }

        .top-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }

        @media (max-width: 768px) {
            .top-row {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: #1C1A18;
            border: 1px solid #2D2A26;
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
            transition: border-color 0.2s ease;
        }

        .card:hover {
            border-color: #3D3631;
        }

        h3 {
            margin: 0 0 16px 0;
            color: #E6E4DE;
            font-weight: 600;
            font-size: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        h3 svg {
            stroke: #C87A53;
        }

        /* Brightness Control */
        .slider-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin: 10px 0;
        }

        .slider-header {
            display: flex;
            justify-content: space-between;
            font-size: 14px;
            color: #969085;
        }

        .slider-header span.val {
            color: #C87A53;
            font-weight: 600;
        }

        input[type=range] {
            width: 100%;
            -webkit-appearance: none;
            background: #2D2A26;
            height: 6px;
            border-radius: 3px;
            outline: none;
        }

        input[type=range]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: #C87A53;
            cursor: pointer;
            transition: transform 0.1s ease;
        }

        input[type=range]::-webkit-slider-thumb:hover {
            transform: scale(1.15);
        }

        /* File Upload Zone */
        .upload-zone {
            border: 2px dashed #2D2A26;
            border-radius: 12px;
            padding: 24px 20px;
            text-align: center;
            cursor: pointer;
            transition: border-color 0.2s ease, background-color 0.2s ease;
            background: rgba(200, 122, 83, 0.01);
        }

        .upload-zone:hover {
            border-color: #C87A53;
            background: rgba(200, 122, 83, 0.03);
        }

        .upload-zone svg {
            width: 32px;
            height: 32px;
            stroke: #C87A53;
            fill: none;
            margin-bottom: 8px;
        }

        .upload-zone p {
            margin: 0;
            font-size: 13px;
            color: #969085;
        }

        .upload-zone p.highlight {
            color: #E6E4DE;
            font-weight: 600;
            margin-bottom: 4px;
        }

        #file-name {
            margin-top: 12px;
            font-size: 13px;
            color: #C87A53;
            font-weight: 600;
            text-align: center;
        }

        /* Responsive Previews Columns */
        .preview-columns {
            display: flex;
            flex-direction: row;
            gap: 24px;
            margin-top: 24px;
            align-items: flex-start;
            justify-content: center;
            width: 100%;
        }

        .preview-column {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
        }

        .column-title {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #969085;
            margin-bottom: 4px;
        }

        video {
            width: 100%;
            max-width: 320px;
            border-radius: 8px;
            border: 1px solid #2D2A26;
            background: #080706;
            aspect-ratio: 26 / 12;
            object-fit: contain;
        }

        #ascii-preview {
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px;
            line-height: 10px;
            background: #080706;
            color: #C87A53;
            border: 1px solid #2D2A26;
            border-radius: 8px;
            padding: 16px;
            width: 100%;
            max-width: 320px;
            height: auto;
            aspect-ratio: 26 / 12;
            text-align: left;
            white-space: pre;
            overflow: hidden;
            box-sizing: border-box;
            box-shadow: inset 0 0 10px rgba(0,0,0,0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }

        @media (max-width: 768px) {
            .preview-columns {
                flex-direction: column;
                align-items: center;
            }
            video, #ascii-preview {
                max-width: 280px;
            }
        }

        /* Buttons & Actions */
        .btn-row {
            display: flex;
            gap: 16px;
            margin-top: 24px;
            width: 100%;
        }

        @media (max-width: 600px) {
            .btn-row {
                flex-direction: column;
            }
        }

        .btn {
            background: #252321;
            border: 1px solid #2D2A26;
            color: #E6E4DE;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
            flex: 1;
            text-align: center;
            box-sizing: border-box;
        }

        .btn:hover:not(:disabled) {
            background: #32302E;
            border-color: #C87A53;
        }

        .btn:active:not(:disabled) {
            transform: scale(0.98);
        }

        .btn:disabled {
            background: #181615;
            color: #5C564E;
            border-color: #252321;
            cursor: not-allowed;
        }

        .btn-accent {
            background: #C87A53;
            color: #E6E4DE;
            border: none;
        }

        .btn-accent:hover:not(:disabled) {
            background: #B36640;
        }

        .btn-accent:disabled {
            background: #3D3631;
            color: #72675C;
        }

        .btn-danger {
            background: rgba(200, 83, 83, 0.05);
            border-color: rgba(200, 83, 83, 0.2);
            color: #E07A7A;
        }

        .btn-danger:hover:not(:disabled) {
            background: #963A3A;
            color: #E6E4DE;
            border-color: #963A3A;
        }

        .action-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        /* Progress Bar */
        .progress-container {
            width: 100%;
            background: #1C1A18;
            height: 6px;
            border-radius: 3px;
            margin-top: 20px;
            overflow: hidden;
            border: 1px solid #2D2A26;
        }

        .progress-bar {
            background: #C87A53;
            width: 0%;
            height: 100%;
            transition: width 0.1s ease;
        }

        #status-text {
            font-size: 13px;
            color: #969085;
            text-align: center;
            margin-top: 12px;
        }

        /* Toast notifications */
        .toast {
            display: none;
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: #1C1A18;
            border: 1px solid #2D2A26;
            color: #E6E4DE;
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideUp 0.2s ease;
        }

        @keyframes slideUp {
            from { transform: translate(-50%, 12px); opacity: 0; }
            to { transform: translate(-50%, 0); opacity: 1; }
        }

        .footer {
            margin-top: 32px;
            text-align: center;
            font-size: 13px;
            color: #5C564E;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .footer a {
            color: #969085;
            text-decoration: none;
            transition: color 0.15s ease;
        }

        .footer a:hover {
            color: #C87A53;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Sprig ASCII Streamer</h1>
        <p>Convert and stream MP4 video to Sprig</p>
    </div>

    <div class="container">
        <!-- Brightness & System controls row -->
        <div class="top-row">
            <!-- Brightness Card -->
            <div class="card">
                <h3>
                    <svg style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
                    Display Brightness
                </h3>
                <div class="slider-container">
                    <div class="slider-header">
                        <span>Backlight Control</span>
                        <span class="val"><span id="bright-val">50</span>%</span>
                    </div>
                    <input type="range" id="bright-range" min="10" max="100" step="10" value="50" onchange="setBrightness(this.value)">
                </div>
            </div>

            <!-- System Controls Card -->
            <div class="card">
                <h3>
                    <svg style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/></svg>
                    Device Controls
                </h3>
                <div class="action-grid">
                    <button class="btn btn-danger" onclick="triggerAction('stop_video')">Hard Stop</button>
                    <button class="btn" onclick="triggerAction('reboot')">Reboot</button>
                </div>
            </div>
        </div>

        <!-- Video Processing Card -->
        <div class="card">
            <h3>
                <svg style="width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;" viewBox="0 0 24 24"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                Video Streamer
            </h3>
            
            <div class="upload-zone" onclick="document.getElementById('video-file').click()">
                <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <p class="highlight">Click to select MP4 video</p>
                <p>Max 15 seconds recommended (20 FPS target)</p>
                <input type="file" id="video-file" accept="video/mp4" style="display:none;" onchange="handleVideoSelect(event)">
            </div>
            <div id="file-name">No file chosen</div>

            <!-- Video Player and ASCII side-by-side columns -->
            <div id="preview-area" style="display:none;">
                <div class="preview-columns">
                    <div class="preview-column">
                        <div class="column-title">Original Video</div>
                        <video id="video-element" controls></video>
                    </div>
                    <div class="preview-column">
                        <div class="column-title">ASCII Preview</div>
                        <div id="ascii-preview">ASCII Preview area</div>
                    </div>
                </div>
                
                <canvas id="ascii-canvas" width="26" height="12" style="display:none;"></canvas>
                
                <div class="btn-row">
                    <button class="btn btn-accent" id="btn-convert" onclick="processVideoToAscii()" disabled>Convert Video</button>
                    <button class="btn btn-accent" id="btn-stream" onclick="streamVideoToSprig()" disabled>Stream to Sprig</button>
                </div>
            </div>

            <div id="progress-container" class="progress-container" style="display:none;">
                <div id="progress-bar" class="progress-bar"></div>
            </div>
            <div id="status-text"></div>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>Created by <a href="https://ionihal.vercel.app" target="_blank">Nihal K</a> (<a href="https://github.com/ioNihal" target="_blank">ioNihal</a>)</p>
            <p><a href="https://github.com/ioNihal/sprig-video2ascii" target="_blank">github.com/ioNihal/sprig-video2ascii</a></p>
        </div>
    </div>

    <div id="toast" class="toast">Command Sent</div>

    <script {nonce}>
        var convertedFrames = [];
        var isConverting = false;
        var isStreaming = false;
        var isConverted = false;
        var animFrameId = null;

        function showToast(text) {
            var toast = document.getElementById('toast');
            toast.innerText = text;
            toast.style.display = 'block';
            setTimeout(function() { toast.style.display = 'none'; }, 3000);
        }

        function setBrightness(val) {
            document.getElementById('bright-val').innerText = val;
            fetch('/brightness?val=' + val)
                .then(r => { if (r.ok) showToast('Brightness set to ' + val + '%'); })
                .catch(() => showToast('Failed to set brightness'));
        }

        function triggerAction(cmd) {
            fetch('/action?cmd=' + cmd)
                .then(r => { 
                    if (r.ok) {
                        showToast(cmd === 'reboot' ? 'Rebooting...' : 'Video Stopped');
                    }
                })
                .catch(() => showToast('Failed to send command'));
        }

        function updateButtonStates() {
            var fileInput = document.getElementById('video-file');
            var hasFile = fileInput.files && fileInput.files.length > 0;
            
            var btnConvert = document.getElementById('btn-convert');
            var btnStream = document.getElementById('btn-stream');
            
            // Convert button: clickable only when media is uploaded, not converting, and not streaming
            btnConvert.disabled = !hasFile || isStreaming || isConverting;
            
            // Stream button: disabled when converting or streaming, or if no converted video exists
            btnStream.disabled = isConverting || isStreaming || !isConverted;
        }

        function handleVideoSelect(event) {
            var file = event.target.files[0];
            if (!file) return;
            document.getElementById('file-name').innerText = file.name;
            var video = document.getElementById('video-element');
            video.src = URL.createObjectURL(file);
            video.load();
            
            // Reset converted states
            convertedFrames = [];
            isConverted = false;
            if (animFrameId) cancelAnimationFrame(animFrameId);
            
            var asciiPreview = document.getElementById('ascii-preview');
            asciiPreview.innerText = "Click 'Convert Video' to generate ASCII preview";
            
            document.getElementById('preview-area').style.display = 'block';
            document.getElementById('status-text').innerText = "Ready to convert";
            
            updateButtonStates();
        }

        function updateAsciiFrame() {
            if (!isConverted || convertedFrames.length === 0) return;
            var video = document.getElementById('video-element');
            var asciiPreview = document.getElementById('ascii-preview');
            
            var fps = 20;
            var frameIdx = Math.floor(video.currentTime * fps);
            
            if (frameIdx >= convertedFrames.length) {
                frameIdx = convertedFrames.length - 1;
            }
            if (frameIdx < 0) {
                frameIdx = 0;
            }
            
            asciiPreview.innerText = convertedFrames[frameIdx];
        }

        // Playback synchronization logic
        var videoElement = document.getElementById('video-element');
        var asciiPreviewElement = document.getElementById('ascii-preview');
        
        asciiPreviewElement.addEventListener('click', function() {
            if (!isConverted) return;
            if (videoElement.paused) {
                videoElement.play();
            } else {
                videoElement.pause();
            }
        });
        
        videoElement.addEventListener('timeupdate', updateAsciiFrame);
        videoElement.addEventListener('seeked', updateAsciiFrame);
        videoElement.addEventListener('seeking', updateAsciiFrame);

        function syncLoop() {
            updateAsciiFrame();
            if (!videoElement.paused && !videoElement.ended) {
                animFrameId = requestAnimationFrame(syncLoop);
            }
        }

        videoElement.addEventListener('play', function() {
            if (animFrameId) cancelAnimationFrame(animFrameId);
            animFrameId = requestAnimationFrame(syncLoop);
        });

        videoElement.addEventListener('pause', function() {
            if (animFrameId) {
                cancelAnimationFrame(animFrameId);
                animFrameId = null;
            }
            updateAsciiFrame();
        });

        async function processVideoToAscii() {
            var video = document.getElementById('video-element');
            var canvas = document.getElementById('ascii-canvas');
            var ctx = canvas.getContext('2d');
            var status = document.getElementById('status-text');
            var progressContainer = document.getElementById('progress-container');
            var progressBar = document.getElementById('progress-bar');
            
            if (!video.duration) { showToast("Wait for video to load"); return; }
            
            isConverting = true;
            isConverted = false;
            convertedFrames = [];
            updateButtonStates();
            
            status.innerText = "Converting video...";
            progressContainer.style.display = 'block';
            progressBar.style.width = '0%';
            
            var totalFrames = Math.floor(Math.min(video.duration, 15.0) * 20);
            var ramp = " .:-=+*#%@";
            
            var origTime = video.currentTime;
            video.pause();
            
            for (var i = 0; i < totalFrames; i++) {
                video.currentTime = i * 0.05;
                await new Promise(r => {
                    var f = function() { video.removeEventListener('seeked', f); r(); };
                    video.addEventListener('seeked', f);
                });
                
                ctx.drawImage(video, 0, 0, 26, 12);
                var d = ctx.getImageData(0, 0, 26, 12).data;
                var frameText = "";
                for (var y = 0; y < 12; y++) {
                    var line = "";
                    for (var x = 0; x < 26; x++) {
                        var idx = (y * 26 + x) * 4;
                        line += ramp[Math.floor((0.299*d[idx] + 0.587*d[idx+1] + 0.114*d[idx+2]) / 255 * (ramp.length - 1))];
                    }
                    frameText += line + "\\n";
                }
                convertedFrames.push(frameText);
                progressBar.style.width = Math.floor(((i + 1) / totalFrames) * 100) + '%';
            }
            
            video.currentTime = 0;
            
            isConverting = false;
            isConverted = true;
            status.innerText = "Conversion complete! Ready to stream.";
            progressContainer.style.display = 'none';
            
            updateAsciiFrame();
            updateButtonStates();
            
            try {
                video.play();
            } catch(e) {
                console.log("Autoplay blocked:", e);
            }
        }

        function streamVideoToSprig() {
            if (!isConverted || convertedFrames.length === 0) return;
            
            isStreaming = true;
            updateButtonStates();
            
            var status = document.getElementById('status-text');
            status.innerText = "Streaming to Sprig...";
            
            var asciiText = convertedFrames.join("");
            
            fetch('/play_ascii', {
                method: 'POST',
                headers: {'Content-Type': 'text/plain'},
                body: asciiText
            })
            .then(r => {
                if (!r.ok) throw new Error("Upload failed");
                return r.json();
            })
            .then(d => {
                if (d.status === 'ok') {
                    showToast("Playing on Sprig!");
                    status.innerText = "Playing on Sprig!";
                } else {
                    showToast(d.message || "Failed to cache video");
                    status.innerText = "Error: " + d.message;
                }
            })
            .catch(e => {
                showToast(e.message || "Upload failed");
                status.innerText = "Upload failed";
            })
            .finally(() => {
                isStreaming = false;
                updateButtonStates();
            });
        }
    </script>
</body>
</html>
"""
    send_all(conn, html)
    conn.close()
