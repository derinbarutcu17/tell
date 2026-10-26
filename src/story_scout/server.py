"""Local dashboard server for Tell.

Binds to 127.0.0.1 only. It serves one HTML file and a small JSON API that
wraps the same pipeline the command line uses.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from story_scout import __version__
from story_scout.model import DEFAULT_MODEL, FREE_MODELS, check_connection
from story_scout.pipeline import ideas_from_store, run_scan
from story_scout.store import Store

ASSETS = Path(__file__).parent / "dashboard_assets"
MODEL_SETTING = "model"


def current_model(store: Store) -> str:
    value = store.get_setting(MODEL_SETTING, DEFAULT_MODEL) or DEFAULT_MODEL
    return value if value in FREE_MODELS else DEFAULT_MODEL


class JobRunner:
    """Runs at most one scan at a time and keeps a log the page can poll."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = 0
        self._state = "idle"
        self._log: list[str] = []
        self._error: str | None = None
        self._id = ""

    def start(self, work: Callable[[Callable[[str], None]], None]) -> str:
        with self._lock:
            if self._state == "running":
                return self._id
            self._counter += 1
            self._id = f"job-{self._counter}"
            self._state = "running"
            self._log = []
            self._error = None
            job_id = self._id

        def append(line: str) -> None:
            with self._lock:
                self._log.append(str(line))

        def body() -> None:
            try:
                work(append)
                with self._lock:
                    self._state = "done"
            except Exception as error:  # noqa: BLE001 - surfaced to the page
                with self._lock:
                    self._state = "error"
                    self._error = f"{type(error).__name__}: {error}"

        threading.Thread(target=body, name=f"tell-{job_id}", daemon=True).start()
        return job_id

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self._id,
                "state": self._state,
                "log": list(self._log),
                "error": self._error,
            }


class TellServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: Store) -> None:
        super().__init__(address, TellHandler)
        self.store = store
        self.jobs = JobRunner()


class TellHandler(BaseHTTPRequestHandler):
    server: TellServer
    server_version = f"Tell/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    # -- helpers ---------------------------------------------------------

    def _send(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        self._send(json.dumps(payload).encode("utf-8"), "application/json", status)

    def _fail(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _state(self) -> dict[str, Any]:
        store = self.server.store
        model = current_model(store)
        return {
            "ideas": ideas_from_store(store),
            "sources": store.list_sources(),
            "settings": {"model": model, "models": sorted(FREE_MODELS)},
            "job": self.server.jobs.snapshot(),
            "version": __version__,
        }

    # -- routing ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            asset = ASSETS / "index.html"
            if not asset.is_file():
                self._fail("dashboard asset is missing", 500)
                return
            self._send(asset.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            self._json(self._state())
            return
        if path == "/api/job":
            self._json({"job": self.server.jobs.snapshot()})
            return
        self._fail("not found", 404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        store = self.server.store
        body = self._body()

        if path == "/api/scan":
            days = body.get("days", 7)
            if not isinstance(days, int) or not 1 <= days <= 365:
                self._fail("days must be an integer between 1 and 365")
                return
            model = current_model(store)

            def work(log: Callable[[str], None]) -> None:
                run_scan(
                    store,
                    days=days,
                    remote=bool(body.get("remote", True)),
                    model=model,
                    log=log,
                )

            job_id = self.server.jobs.start(work)
            self._json({"job": {"id": job_id, "state": "running", "log": []}})
            return

        if path.startswith("/api/ideas/") and path.endswith("/status"):
            raw_id = path[len("/api/ideas/") : -len("/status")]
            if not raw_id.isdigit():
                self._fail("idea id must be a number")
                return
            status = str(body.get("status") or "")
            if status not in ("new", "kept", "rejected"):
                self._fail("status must be new, kept, or rejected")
                return
            if not store.set_status(int(raw_id), status):
                self._fail("no idea with that id", 404)
                return
            self._json({"ok": True, "status": status})
            return

        if path == "/api/settings":
            model = str(body.get("model") or "").strip()
            if model not in FREE_MODELS:
                self._fail("only free models are allowed")
                return
            store.set_setting(MODEL_SETTING, model)
            self._json({"ok": True, "model": model})
            return

        if path == "/api/test-connection":
            model = str(body.get("model") or current_model(store)).strip()
            ok, message = check_connection(model)
            self._json({"ok": ok, "message": message})
            return

        if path == "/api/sources":
            raw_path = str(body.get("path") or "").strip()
            if not raw_path:
                self._fail("a folder path is required")
                return
            try:
                source_id = store.add_source(Path(raw_path).expanduser())
            except (OSError, ValueError) as error:
                self._fail(str(error))
                return
            self._json({"ok": True, "id": source_id})
            return

        self._fail("not found", 404)

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        prefix = "/api/sources/"
        if path.startswith(prefix):
            raw_id = path[len(prefix) :]
            if not raw_id.isdigit():
                self._fail("source id must be a number")
                return
            if not self.server.store.remove_source(int(raw_id)):
                self._fail("no source with that id", 404)
                return
            self._json({"ok": True})
            return
        self._fail("not found", 404)


def serve(store: Store, *, port: int = 8765, open_browser: bool = True) -> int:
    """Run the dashboard until interrupted."""
    server: TellServer | None = None
    chosen = port
    for candidate in range(port, port + 6):
        try:
            server = TellServer(("127.0.0.1", candidate), store)
            chosen = candidate
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"no free port between {port} and {port + 5}")
    url = f"http://127.0.0.1:{chosen}/"
    print(f"Tell dashboard: {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0
