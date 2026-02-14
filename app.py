import cgi
import json
from urllib.parse import parse_qs
import os
import re
import shlex
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional


class DownloadState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process: Optional[subprocess.Popen] = None
        self.stdout_thread: Optional[threading.Thread] = None
        self.last_log = ""
        self.progress = "0%"
        self.speed = "-"
        self.eta = "-"
        self.status = "idle"
        self.error = ""
        self.command = ""


STATE = DownloadState()
PROGRESS_RE = re.compile(r"\((\d+%)\).+DL:([^ ]+).+ETA:([^\]]+)")
BASE_DIR = Path(__file__).resolve().parent


def read_text(rel_path: str) -> bytes:
    return (BASE_DIR / rel_path).read_bytes()


def _read_output(proc: subprocess.Popen) -> None:
    try:
        assert proc.stdout is not None
        for raw_line in iter(proc.stdout.readline, ""):
            line = raw_line.strip()
            if not line:
                continue
            with STATE.lock:
                STATE.last_log = line
                matched = PROGRESS_RE.search(line)
                if matched:
                    STATE.progress = matched.group(1)
                    STATE.speed = matched.group(2)
                    STATE.eta = matched.group(3)
        code = proc.wait()
        with STATE.lock:
            if code == 0:
                STATE.status = "completed"
            elif STATE.status != "stopped":
                STATE.status = "failed"
                STATE.error = f"aria2c exited with code {code}"
    except Exception as exc:
        with STATE.lock:
            STATE.status = "failed"
            STATE.error = str(exc)


def _find_aria2() -> str:
    return os.environ.get("ARIA2C_PATH", "aria2c")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str = "text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: dict):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path == "/":
            self._send(200, read_text("templates/index.html"), "text/html; charset=utf-8")
            return
        if self.path == "/static/app.js":
            self._send(200, read_text("static/app.js"), "application/javascript; charset=utf-8")
            return
        if self.path == "/api/status":
            with STATE.lock:
                self._json(
                    200,
                    {
                        "status": STATE.status,
                        "progress": STATE.progress,
                        "speed": STATE.speed,
                        "eta": STATE.eta,
                        "last_log": STATE.last_log,
                        "error": STATE.error,
                        "command": STATE.command,
                    },
                )
            return
        self._json(404, {"ok": False, "message": "Not found"})

    def do_POST(self):
        if self.path == "/api/start":
            self.handle_start()
            return
        if self.path == "/api/stop":
            self.handle_stop()
            return
        self._json(404, {"ok": False, "message": "Not found"})

    def _parse_form(self):
        ctype, _ = cgi.parse_header(self.headers.get("Content-Type", ""))
        if ctype.startswith("multipart/form-data"):
            fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
            torrent_url = fs.getvalue("torrent_url", "")
            download_dir = fs.getvalue("download_dir", "")
            torrent_file = fs["torrent_file"] if "torrent_file" in fs else None
            return torrent_url, download_dir, torrent_file

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw)
        return parsed.get("torrent_url", [""])[0], parsed.get("download_dir", [""])[0], None

    def handle_start(self):
        with STATE.lock:
            if STATE.process and STATE.process.poll() is None:
                self._json(400, {"ok": False, "message": "A task is already running."})
                return

        torrent_url, download_dir, torrent_file = self._parse_form()
        save_dir = str(download_dir).strip()
        if not save_dir:
            self._json(400, {"ok": False, "message": "download_dir is required."})
            return

        target_dir = Path(save_dir).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)

        temp_torrent = None
        input_arg = ""
        if torrent_file is not None and getattr(torrent_file, "filename", ""):
            fd, temp_torrent = tempfile.mkstemp(suffix=".torrent")
            os.close(fd)
            with open(temp_torrent, "wb") as f:
                f.write(torrent_file.file.read())
            input_arg = temp_torrent
        elif str(torrent_url).strip():
            input_arg = str(torrent_url).strip()
        else:
            self._json(400, {"ok": False, "message": "torrent_url or torrent_file is required."})
            return

        cmd = [
            _find_aria2(),
            "--seed-time=0",
            "--max-upload-limit=1K",
            "--dir",
            str(target_dir),
            "--summary-interval=1",
            "--console-log-level=notice",
            input_arg,
        ]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except FileNotFoundError:
            if temp_torrent and os.path.exists(temp_torrent):
                os.unlink(temp_torrent)
            self._json(
                500,
                {
                    "ok": False,
                    "message": "aria2c not found. Please install aria2 and ensure aria2c is in PATH, or set ARIA2C_PATH.",
                },
            )
            return

        with STATE.lock:
            STATE.process = proc
            STATE.progress = "0%"
            STATE.speed = "-"
            STATE.eta = "-"
            STATE.status = "downloading"
            STATE.error = ""
            STATE.command = " ".join(shlex.quote(c) for c in cmd)
            STATE.last_log = "Task started"
            STATE.stdout_thread = threading.Thread(target=_read_output, args=(proc,), daemon=True)
            STATE.stdout_thread.start()

        self._json(200, {"ok": True, "message": "Download started."})

    def handle_stop(self):
        with STATE.lock:
            proc = STATE.process
            if not proc or proc.poll() is not None:
                self._json(400, {"ok": False, "message": "No running task."})
                return
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
            except Exception:
                proc.kill()
            STATE.status = "stopped"
        self._json(200, {"ok": True, "message": "Stop signal sent."})


def run():
    server = ThreadingHTTPServer(("0.0.0.0", 5000), Handler)
    print("Server running at http://127.0.0.1:5000")
    server.serve_forever()


if __name__ == "__main__":
    run()
