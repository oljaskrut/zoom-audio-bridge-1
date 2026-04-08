import json
import os
import threading
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse
from urllib.request import urlopen, Request

import numpy as np
import pyaudiowpatch as pyaudio
import win32gui
import websockets.sync.client as ws_client
from dotenv import load_dotenv

load_dotenv()

CHUNK = 1024
FORMAT = pyaudio.paInt16
ZOOM_CHECK_INTERVAL_S = 2
ZOOM_WINDOW_CLASSES = {
    "ConfMultiTabContentWndClass",
    "ZPToolBarParentWndClass",
    "ZPPTMainFrmWndClassEx",
    "ZPFloatVideoWndClass",
    "ZPMeetingWndClass",
    "ZPMainWndClass",
}


def is_zoom_running() -> bool:
    found = [False]

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if cls in ZOOM_WINDOW_CLASSES or ("zoom" in title.lower() and cls.startswith("ZP")):
                found[0] = True
                return False  # stop enumeration

    win32gui.EnumWindows(callback, None)
    return found[0]


def check_server_health(base_url: str) -> tuple[bool, str]:
    """Ping the /api/health endpoint. Returns (ok, message)."""
    parsed = urlparse(base_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    health_url = f"{scheme}://{parsed.netloc}/api/health"
    try:
        req = Request(health_url, method="GET")
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "ok":
                return True, "Server healthy"
            return False, f"Server status: {data.get('status')}"
    except Exception as e:
        return False, f"Health check failed: {e}"


WS_PING_INTERVAL_S = 20
WS_PING_TIMEOUT_S = 10
WS_RECONNECT_DELAYS = [1, 2, 4, 8, 16]  # exponential backoff, max 16s


def stream_audio(ws_url: str, stop_event: threading.Event, wave_callback=None,
                 status_callback=None):
    p = pyaudio.PyAudio()
    try:
        loopback = p.get_default_wasapi_loopback()
        device_rate = int(loopback["defaultSampleRate"])
        device_channels = loopback["maxInputChannels"]

        stream = p.open(
            format=FORMAT,
            channels=device_channels,
            rate=device_rate,
            input=True,
            input_device_index=loopback["index"],
            frames_per_buffer=CHUNK,
        )

        send_every = max(1, int(0.05 * device_rate / CHUNK))  # ~50ms
        zoom_check_every = max(1, int(ZOOM_CHECK_INTERVAL_S * device_rate / CHUNK))
        reconnect_attempt = 0

        while not stop_event.is_set() and is_zoom_running():
            try:
                ws = ws_client.connect(
                    ws_url,
                    ping_interval=WS_PING_INTERVAL_S,
                    ping_timeout=WS_PING_TIMEOUT_S,
                    close_timeout=5,
                )
            except Exception as e:
                delay = WS_RECONNECT_DELAYS[min(reconnect_attempt, len(WS_RECONNECT_DELAYS) - 1)]
                if status_callback:
                    status_callback(f"Connection failed, retrying in {delay}s...")
                reconnect_attempt += 1
                stop_event.wait(delay)
                continue

            reconnect_attempt = 0
            if status_callback:
                status_callback("Streaming audio...")
            buffer: list[np.ndarray] = []
            chunk_count = 0

            try:
                while not stop_event.is_set():
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    mono = np.frombuffer(data, dtype=np.int16)
                    if device_channels == 2:
                        mono = mono.reshape(-1, 2).mean(axis=1).astype(np.int16)

                    buffer.append(mono)
                    chunk_count += 1

                    if chunk_count % send_every == 0:
                        batch = np.concatenate(buffer)
                        buffer.clear()
                        ws.send(batch.tobytes())
                        if wave_callback:
                            wave_callback(batch)

                    if chunk_count % zoom_check_every == 0 and not is_zoom_running():
                        break

                try:
                    if buffer:
                        batch = np.concatenate(buffer)
                        ws.send(batch.tobytes())
                        buffer.clear()
                    if not stop_event.is_set():
                        ws.send(json.dumps({"type": "stop_transcription"}))
                except Exception:
                    pass
                break  # clean exit — Zoom closed or stop requested
            except Exception:
                # WebSocket died mid-stream — reconnect without restarting audio
                if status_callback:
                    status_callback("Connection lost, reconnecting...")
                continue
            finally:
                try:
                    ws.close()
                except Exception:
                    pass
    finally:
        if "stream" in locals():
            stream.stop_stream()
            stream.close()
        p.terminate()


class App:
    _WAVE_WIDTH = 300
    _WAVE_HEIGHT = 60

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zoom Audio Bridge")
        self.root.resizable(False, False)

        self.stop_event = threading.Event()
        self.stop_event.set()  # starts in stopped state
        self.worker: threading.Thread | None = None
        self._wave_points: list[float] = []

        frame = ttk.Frame(root, padding=16)
        frame.pack()

        # Server URL
        ttk.Label(frame, text="Server URL").grid(row=0, column=0, sticky="w")
        self.server_url = tk.StringVar(value=os.getenv("SERVER_URL", ""))
        url_row = ttk.Frame(frame)
        url_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.url_entry = ttk.Entry(url_row, textvariable=self.server_url, width=32)
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.health_btn = ttk.Button(url_row, text="Check", command=self._check_health)
        self.health_btn.pack(side="left", padx=(8, 0))

        # Waveform display
        self.wave_canvas = tk.Canvas(
            frame, width=self._WAVE_WIDTH, height=self._WAVE_HEIGHT,
            bg="#111", highlightthickness=0,
        )
        self.wave_canvas.grid(row=2, column=0, columnspan=2, pady=(0, 12))
        self._wave_line = self.wave_canvas.create_line(
            0, self._WAVE_HEIGHT // 2, self._WAVE_WIDTH, self._WAVE_HEIGHT // 2,
            fill="#4caf50", width=1,
        )

        # Status
        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(frame, textvariable=self.status_var, font=("default", 10))
        self.status_label.grid(row=3, column=0, columnspan=2, pady=(0, 12))

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2)
        self.start_btn = ttk.Button(btn_frame, text="Start", command=self.start)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def set_status(self, text: str):
        self.status_var.set(text)

    def _build_ws_url(self) -> str:
        base = self.server_url.get().strip().rstrip("/")
        parsed = urlparse(base)
        if parsed.scheme in ("http", "https"):
            scheme = "wss" if parsed.scheme == "https" else "ws"
            base = f"{scheme}://{parsed.netloc}"
        return f"{base}/ws/audio"

    def _check_health(self):
        self.set_status("Checking server...")
        threading.Thread(target=self._do_health_check, daemon=True).start()

    def _do_health_check(self):
        ws_url = self._build_ws_url()
        ok, msg = check_server_health(ws_url)
        self.root.after(0, self.set_status, msg)

    def _update_waveform(self):
        if self.stop_event.is_set():
            mid = self._WAVE_HEIGHT // 2
            self.wave_canvas.coords(self._wave_line, 0, mid, self._WAVE_WIDTH, mid)
            return
        points = self._wave_points
        if len(points) >= 4:
            self.wave_canvas.coords(self._wave_line, *points)
        self.root.after(50, self._update_waveform)

    def _on_wave(self, samples: np.ndarray):
        w = self._WAVE_WIDTH
        h = self._WAVE_HEIGHT
        mid = h // 2
        step = max(1, len(samples) // w)
        downsampled = samples[::step][:w].astype(np.float32) / 32768.0
        x = np.linspace(0, w, len(downsampled))
        y = mid - downsampled * mid
        self._wave_points = np.column_stack((x, y)).ravel().tolist()

    def start(self):
        base = self.server_url.get().strip()
        if not base:
            self.set_status("Enter a server URL")
            return

        self.stop_event.clear()
        self._wave_points = []
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.url_entry.config(state="disabled")
        self.health_btn.config(state="disabled")
        self.set_status("Checking server...")
        self._update_waveform()

        ws_url = self._build_ws_url()
        self.worker = threading.Thread(target=self._run, args=(ws_url,), daemon=True)
        self.worker.start()

    def stop(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self._wave_points = []
        mid = self._WAVE_HEIGHT // 2
        self.wave_canvas.coords(self._wave_line, 0, mid, self._WAVE_WIDTH, mid)
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.url_entry.config(state="normal")
        self.health_btn.config(state="normal")
        self.set_status("Idle")

    def _set_status_safe(self, text: str):
        self.root.after(0, self.set_status, text)

    def _run(self, ws_url: str):
        try:
            ok, msg = check_server_health(ws_url)
            if not ok:
                self._set_status_safe(msg)
                return

            self._set_status_safe("Waiting for Zoom...")
            while not self.stop_event.is_set():
                if is_zoom_running():
                    try:
                        stream_audio(ws_url, self.stop_event, self._on_wave,
                                     self._set_status_safe)
                    except Exception as e:
                        self._set_status_safe(f"Error: {e}")
                        self.stop_event.wait(3)
                        continue
                    self._set_status_safe("Zoom ended. Waiting...")
                self.stop_event.wait(ZOOM_CHECK_INTERVAL_S)
        finally:
            self.root.after(0, self.stop)

    def on_close(self):
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
