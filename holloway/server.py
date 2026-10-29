"""Localhost viewer: watches a scene script, rebuilds it, pushes updates to the browser.

Standard library only. Rebuilds run in a subprocess (python -m holloway.build),
and the browser is told about new builds via Server-Sent Events.
"""

import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / "static"
PACKAGE = Path(__file__).parent
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class State:
    def __init__(self, script: Path) -> None:
        self.script = script
        self.version = 0
        self.status = "building"
        self.payload = b"{}"
        self.cond = threading.Condition()

    def publish(self, status: str, payload: bytes | None = None) -> None:
        with self.cond:
            self.version += 1
            self.status = status
            if payload is not None:
                self.payload = payload
            self.cond.notify_all()

    def rebuild(self) -> None:
        self.publish("building")
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "holloway.build", str(self.script)],
                capture_output=True,
                timeout=600,
                cwd=self.script.parent,
            )
        except subprocess.TimeoutExpired:
            self.publish("error", json.dumps({"error": "build timed out after 600s"}).encode())
            return
        if proc.stderr:
            sys.stderr.write(proc.stderr.decode(errors="replace"))
        dt = time.perf_counter() - t0
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            data["name"] = self.script.name
            print(f"[holloway] built {self.script.name} in {dt:.2f}s: {data['stats']}", flush=True)
            self.publish("ready", json.dumps(data).encode())
        else:
            err = proc.stderr.decode(errors="replace").strip() or f"exit code {proc.returncode}"
            print(f"[holloway] build failed ({dt:.2f}s)", flush=True)
            self.publish("error", json.dumps({"error": err, "name": self.script.name}).encode())


def snapshot(roots: list[Path]) -> dict[Path, float]:
    files = {}
    for root in roots:
        for p in root.rglob("*.py"):
            if any(part.startswith(".") or part == "__pycache__" for part in p.parts):
                continue
            try:
                files[p] = p.stat().st_mtime
            except FileNotFoundError:
                pass
    return files


def watch(state: State) -> None:
    roots = [state.script.parent, PACKAGE]
    seen = None
    while True:
        snap = snapshot(roots)
        if snap != seen:
            time.sleep(0.05)  # let editors finish writing
            seen = snapshot(roots)
            state.rebuild()
        time.sleep(0.25)


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args) -> None:
            pass

        def send_bytes(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path == "/":
                path = "/static/index.html"
            if path == "/scene":
                with state.cond:
                    body = state.payload
                self.send_bytes(body, "application/json")
            elif path == "/events":
                self.events()
            elif path.startswith("/static/"):
                f = (STATIC / path.removeprefix("/static/")).resolve()
                if f.is_relative_to(STATIC) and f.is_file():
                    self.send_bytes(f.read_bytes(), CONTENT_TYPES.get(f.suffix, "application/octet-stream"))
                else:
                    self.send_error(404)
            else:
                self.send_error(404)

        def events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last = -1
            try:
                while True:
                    with state.cond:
                        state.cond.wait_for(lambda: state.version != last, timeout=15)
                        version, status = state.version, state.status
                    if version == last:
                        self.wfile.write(b": keep-alive\n\n")
                    else:
                        last = version
                        self.wfile.write(f"data: {json.dumps({'version': version, 'status': status})}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def serve(script: str, port: int = 8000, open_browser: bool = True) -> None:
    path = Path(script).resolve()
    if not path.is_file():
        raise SystemExit(f"no such scene script: {script}")
    state = State(path)
    threading.Thread(target=watch, args=(state,), daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"[holloway] serving {path.name} at {url} (watching {path.parent} for changes)", flush=True)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
