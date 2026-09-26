"""Launch the local app and open its browser after the server is ready."""
import argparse
import json
from pathlib import Path
import socket
import sys
import threading
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
URL = "http://127.0.0.1:8769"


def app_ready():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL + "/api/config", timeout=1) as response:
            config = json.load(response)
        return config.get("languages") == ["bs", "hr", "sr"] and "large-v3-turbo" in config.get("models", [])
    except (OSError, ValueError, AttributeError):
        return False


def open_when_ready(stopped, ready=app_ready, open_url=webbrowser.open, attempts=60):
    for _ in range(attempts):
        if stopped.is_set():
            return
        if ready():
            open_url(URL)
            return
        if stopped.wait(.5):
            return
    print(f"Browser did not open automatically. Open {URL} after the server is ready.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true', help='Start without opening a browser')
    args = parser.parse_args(argv)
    if app_ready():
        print(f"The app is already running: {URL}")
        if not args.no_browser:
            webbrowser.open(URL)
        return 0
    try:
        with socket.create_connection(("127.0.0.1", 8769), timeout=1):
            print("Port 8769 is already in use by another service. Stop that service and try again.")
            return 1
    except OSError:
        pass
    try:
        import uvicorn
    except ImportError:
        print("App dependencies are missing. Run install.bat first.")
        return 1
    print(f"Starting {URL}. Keep this window open; press Ctrl+C to stop.", flush=True)
    stopped = threading.Event()
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(stopped,), daemon=True).start()
    try:
        uvicorn.run("stt.app:create_app", factory=True, host="127.0.0.1", port=8769)
    finally:
        stopped.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
