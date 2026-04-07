import json
import os
import time
import threading
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse
from urllib.request import urlopen, Request

import numpy as np
import pyaudiowpatch as pyaudio
from scipy.signal import resample_poly
import win32gui
import websockets.sync.client as ws_client
from dotenv import load_dotenv

load_dotenv()

CHUNK = 1024
FORMAT = pyaudio.paInt16
SAMPLE_RATE = 32000
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
    found = []

    def callback(hwnd, acc):
        if win32gui.IsWindowVisible(hwnd):
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if cls in ZOOM_WINDOW_CLASSES or ("zoom" in title.lower() and cls.startswith("ZP")):
                acc.append(hwnd)

    win32gui.EnumWindows(callback, found)
    return len(found) > 0


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


def stream_audio(ws_url: str, stop_event: threading.Event, level_callback=None):
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

        from math import gcd
        g = gcd(device_rate, SAMPLE_RATE)
        up = SAMPLE_RATE // g
        down = device_rate // g

        with ws_client.connect(ws_url) as ws:
            while not stop_event.is_set() and is_zoom_running():
                data = stream.read(CHUNK, exception_on_overflow=False)
                mono = np.frombuffer(data, dtype=np.int16)
                if device_channels == 2:
                    mono = mono.reshape(-1, 2).mean(axis=1).astype(np.int16)
                if device_rate != SAMPLE_RATE:
                    mono = resample_poly(mono, up, down).astype(np.int16)
                if level_callback:
                    rms = np.sqrt(np.mean(mono.astype(np.float32) ** 2))
                    level_callback(min(rms / 32768.0, 1.0))
                ws.send(mono.tobytes())

            # tell server we're done
            if not stop_event.is_set():
                try:
                    ws.send(json.dumps({"type": "stop_transcription"}))
                except Exception:
                    pass
    finally:
        if "stream" in locals():
            stream.stop_stream()
            stream.close()
        p.terminate()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zoom Audio Bridge")
        self.root.resizable(False, False)

        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._level = 0.0

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

        # Level meter
        self.meter = tk.Canvas(frame, width=300, height=20, bg="#222", highlightthickness=0)
        self.meter.grid(row=2, column=0, columnspan=2, pady=(0, 12))
        self._meter_bar = self.meter.create_rectangle(0, 0, 0, 20, fill="#4caf50", width=0)

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

    def _update_meter(self):
        if self.stop_event.is_set():
            self.meter.coords(self._meter_bar, 0, 0, 0, 20)
            return
        width = int(self._level * 300)
        color = "#4caf50" if self._level < 0.6 else "#ff9800" if self._level < 0.85 else "#f44336"
        self.meter.coords(self._meter_bar, 0, 0, width, 20)
        self.meter.itemconfig(self._meter_bar, fill=color)
        self.root.after(50, self._update_meter)

    def _on_level(self, level: float):
        self._level = level

    def start(self):
        base = self.server_url.get().strip()
        if not base:
            self.set_status("Enter a server URL")
            return

        self.stop_event.clear()
        self._level = 0.0
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.url_entry.config(state="disabled")
        self.health_btn.config(state="disabled")
        self.set_status("Checking server...")
        self._update_meter()

        ws_url = self._build_ws_url()
        self.worker = threading.Thread(target=self._run, args=(ws_url,), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self._level = 0.0
        self.meter.coords(self._meter_bar, 0, 0, 0, 20)
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.url_entry.config(state="normal")
        self.health_btn.config(state="normal")
        self.set_status("Idle")

    def _run(self, ws_url: str):
        try:
            ok, msg = check_server_health(ws_url)
            if not ok:
                self.root.after(0, self.set_status, msg)
                return

            self.root.after(0, self.set_status, "Waiting for Zoom...")
            while not self.stop_event.is_set():
                if is_zoom_running():
                    self.root.after(0, self.set_status, "Streaming audio...")
                    try:
                        stream_audio(ws_url, self.stop_event, self._on_level)
                    except Exception as e:
                        self.root.after(0, self.set_status, f"Error: {e}")
                        time.sleep(3)
                        continue
                    self.root.after(0, self.set_status, "Zoom ended. Waiting...")
                time.sleep(ZOOM_CHECK_INTERVAL_S)
        finally:
            self.root.after(0, self.stop)

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
