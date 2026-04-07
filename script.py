# ── Bootstrap: auto-install required packages before anything else ──────────
import subprocess
import sys

_REQUIRED = [
    "python-dotenv",
    "pywin32",
    "PyAudioWPatch",
    "soniox",
    "numpy",
]

def _ensure_packages():
    import importlib.util
    _import_map = {
        "python-dotenv": "dotenv",
        "pywin32":       "win32gui",
        "PyAudioWPatch": "pyaudiowpatch",
        "soniox":        "soniox",
        "numpy":         "numpy",
    }
    missing = [pkg for pkg, mod in _import_map.items()
               if importlib.util.find_spec(mod) is None]
    if missing:
        print(f"Installing missing packages: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("Installation complete.\n")

_ensure_packages()
# ─────────────────────────────────────────────────────────────────────────────

import time
import threading
import os
from pathlib import Path
import numpy as np

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

import win32gui # to interact with Windows GUI
import pyaudiowpatch as pyaudio # to capture audio
from soniox import SonioxClient # to transcribe audio
from soniox.types import RealtimeSTTConfig

# Configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
ZOOM_WINDOW_CLASSES = {"ZPFloatVideoWndClass", "ZPMeetingWndClass", "ZPMainWndClass"}

def is_zoom_meeting_running():
    """Check if a Zoom meeting is currently running."""
    def callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if ('zoom' in title.lower() and class_name.startswith('ZP')) or class_name in ZOOM_WINDOW_CLASSES:
                windows.append(hwnd)
    windows = []
    win32gui.EnumWindows(callback, windows)
    return len(windows) > 0

def capture_wasapi_loop(session, stop_event, device_rate, device_channels):
    """Capture audio from the default WASAPI loopback device."""
    p = pyaudio.PyAudio()

    try:
        loopback_device = p.get_default_wasapi_loopback()

        stream = p.open(format=FORMAT,
                        channels=device_channels,
                        rate=device_rate,
                        input=True,
                        input_device_index=loopback_device['index'],
                        frames_per_buffer=CHUNK)

        print(f"Successfully hooked into Windows Audio: {loopback_device['name']}")

        while not stop_event.is_set() and is_zoom_meeting_running():
            data = stream.read(CHUNK, exception_on_overflow=False)
            # Convert stereo to mono before sending — Soniox transcribes mono
            if device_channels == 2:
                samples = np.frombuffer(data, dtype=np.int16).reshape(-1, 2)
                data = samples.mean(axis=1).astype(np.int16).tobytes()
            try:
                session.send_bytes(data)
            except Exception:
                break
    except Exception as e:
        if not stop_event.is_set():
            print(f"Audio Error: {e}")
    finally:
        if 'stream' in locals():
            stream.stop_stream()
            stream.close()
        p.terminate()


def run_transcription():
    """Run the Soniox real-time transcription."""
    # Resolve actual device settings before opening the Soniox session
    _p = pyaudio.PyAudio()
    try:
        _dev = _p.get_default_wasapi_loopback()
        device_rate = int(_dev["defaultSampleRate"])
        device_channels = _dev["maxInputChannels"]
    finally:
        _p.terminate()

    client = SonioxClient(api_key=os.environ["SONIOX_API_KEY"])
    config = RealtimeSTTConfig(
        model="stt-rt-v4",
        audio_format="pcm_s16le",
        sample_rate=device_rate,
        num_channels=1  # audio thread converts stereo -> mono before sending
    )

    stop_event = threading.Event()

    with client.realtime.stt.connect(config=config) as session:
        print("Connected to Soniox real-time STT service. Transcribing audio...")

        audio_thread = threading.Thread(
            target=capture_wasapi_loop,
            args=(session, stop_event, device_rate, device_channels),
            daemon=True
        )
        audio_thread.start()

        try:
            final_text = ""
            for event in session.receive_events():
                # stop if zoom closes
                if not is_zoom_meeting_running():
                    print("\nZoom meeting ended. Stopping transcription.")
                    break

                interim_transcript = ""
                final_transcript = ""

                for token in event.tokens:
                    if token.is_final:
                        final_transcript += token.text
                    else:
                        interim_transcript += token.text
                if final_transcript:
                    final_text += final_transcript
                print(f"\r{final_text}{interim_transcript}     ", end="", flush=True)
        except Exception as e:
            print(f"\nTranscription Error: {e}")
        finally:
            stop_event.set()

    print()

def main():
    if not os.getenv("SONIOX_API_KEY"):
        print("SONIOX_API_KEY is missing. Please set it in your .env file.")
        return

    print("Listening for Zoom Meetings to start ...")
    print("Press Ctrl+C to stop.\n")

    # background loop watching for zoom meetings to start
    try:
        while True:
            if is_zoom_meeting_running():
                print("Zoom meeting detected. Starting transcription...")
                try:
                    run_transcription()
                except Exception as e:
                    print(f"Connection error: {e}. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                print("Transcription stopped. Waiting for next Zoom meeting...")
                time.sleep(1)
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == "__main__":
    main()