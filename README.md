# Zoom Audio Bridge

Captures Zoom meeting audio via WASAPI loopback and streams it over WebSocket to a transcription server.

## Requirements

- Windows 10/11
- Python 3.11+ ([download](https://www.python.org/downloads/)) — check "Add to PATH" during installation

## Setup

```bat
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set your server URL:

```
SERVER_URL=http://localhost:3000
```

## Run

```bat
python app.py
```

Or use the batch files:

1. `setup.bat` — installs dependencies
2. `start.bat` — launches the app
