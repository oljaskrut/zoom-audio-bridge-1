# Zoom Audio Bridge

Captures Zoom meeting audio via WASAPI loopback and streams it over WebSocket to a transcription server.

## Requirements

- Windows 10/11
- Python 3.12.8 ([download installer](https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe)) — check "Add to PATH" during installation

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
