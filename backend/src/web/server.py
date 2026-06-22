"""Tiny stdlib HTTP server that bridges the TRIDENT web UI to the offline engine.

No third-party web framework: it uses ``http.server`` so it runs on the base
install (pydantic + PyYAML) with zero extra dependencies. It serves the single
frontend HTML file at ``/`` and exposes a small JSON API the page calls:

    GET  /api/health              -> capability probe (engine.health)
    GET  /api/packages            -> catalog packages for the planning UI
    GET  /api/techniques          -> catalog technique labels (name/owasp/atlas) for the report
    GET  /api/logstream           -> Server-Sent Events: live engine logs for the
                                     web "terminal" mode
    POST /api/plan                -> one advisor turn: propose packages OR ask
                                     clarifying questions (propose / clarify)
    POST /api/campaign            -> run a recon/attack campaign, return the
                                     real trace.jsonl text + correlate() report

Run it with:

    python -m src.web.server                       # http://localhost:8765
    python -m src.web.server --port 9000
    python -m src.web.server --frontend "..\\my.html"

Everything is same-origin (page + API on one port), so the browser needs no CORS
exception; permissive CORS headers are still sent so the API also works if the
HTML is opened from elsewhere.
"""
from __future__ import annotations

import argparse
import json
import logging
import queue
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from . import engine
from .logbus import BUS

log = logging.getLogger("trident.web")

_ROOT = Path(__file__).resolve().parents[2]
# Repo layout: <repo>/backend/src/web/server.py and <repo>/frontend/frontend.html.
# _ROOT is the backend/ dir; the UI lives in the sibling frontend/ folder.
_DEFAULT_FRONTEND = _ROOT.parent / "frontend" / "frontend.html"
_MAX_BODY = 1 * 1024 * 1024  # 1 MiB cap on request bodies


class TridentHandler(BaseHTTPRequestHandler):
    server_version = "TridentWeb/0.3"
    frontend_path: Path = _DEFAULT_FRONTEND          # overridden in main()

    # ---- helpers ------------------------------------------------------
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str = "text/html; charset=utf-8",
                   status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > _MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) or {}

    def log_message(self, fmt: str, *args) -> None:  # quieter default logging
        log.info("%s - %s", self.address_string(), fmt % args)

    # ---- routes -------------------------------------------------------
    def do_OPTIONS(self) -> None:                    # CORS preflight
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_frontend()
        if path == "/api/health":
            return self._send_json(engine.health())
        if path == "/api/packages":
            return self._send_json({"packages": engine.list_packages()})
        if path == "/api/techniques":
            return self._send_json({"techniques": engine.list_techniques()})
        if path == "/api/logstream":
            return self._serve_logstream()
        self._send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in ("/api/campaign", "/api/plan"):
            return self._send_json({"error": "not found", "path": path}, status=404)
        try:
            body = self._read_json_body()
        except Exception as exc:
            return self._send_json({"error": f"bad request: {exc}"}, status=400)

        if path == "/api/plan":
            history = body.get("history") or []
            mode = str(body.get("mode") or "attack").strip().lower()
            if not isinstance(history, list):
                return self._send_json({"error": "history must be a list"}, status=400)
            try:
                return self._send_json(engine.plan(history, mode=mode))
            except Exception as exc:
                log.exception("plan failed")
                return self._send_json({"error": f"plan failed: {exc}"}, status=500)

        # /api/campaign
        prompt = str(body.get("prompt") or "").strip()
        mode = str(body.get("mode") or "attack").strip().lower()
        package_id = body.get("package") or body.get("package_id") or None
        if package_id:
            package_id = str(package_id)

        try:
            result = engine.run_campaign(prompt, mode=mode, package_id=package_id)
        except Exception as exc:
            log.exception("campaign failed")
            return self._send_json({"error": f"campaign failed: {exc}"}, status=500)
        self._send_json(result)

    # ---- static frontend ---------------------------------------------
    def _serve_frontend(self) -> None:
        try:
            html = self.frontend_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._send_text(
                f"<h1>Frontend not found</h1><p>Expected at:<br><code>{self.frontend_path}</code>"
                f"</p><p>Pass <code>--frontend &lt;path&gt;</code> to point at the HTML file.</p>",
                status=404,
            )
        self._send_text(html)

    # ---- live log stream (SSE) ---------------------------------------
    def _sse_send(self, item: dict) -> None:
        payload = json.dumps(item, default=str)
        self.wfile.write(b"data: " + payload.encode("utf-8") + b"\n\n")
        self.wfile.flush()

    def _serve_logstream(self) -> None:
        """Server-Sent Events stream of the engine's live logs for the web
        terminal. The threaded server keeps this open while a campaign runs on
        another connection, so the UI sees dispatch/judge/HTTP activity in real
        time. Replays a short backlog on connect, then streams with a heartbeat.
        """
        self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        q = BUS.subscribe()
        try:
            for item in BUS.snapshot():
                self._sse_send(item)
            self._sse_send({"ts": time.time(), "level": "INFO",
                            "logger": "trident.web", "msg": "live stream connected"})
            while True:
                try:
                    item = q.get(timeout=15.0)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self._sse_send(item)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            BUS.unsubscribe(q)
            self.close_connection = True


def main(argv: list[str] | None = None) -> None:
    load_dotenv()  # pick up FOUNDRY_* / AIGOAT_* from a local .env (same as the CLI)
    p = argparse.ArgumentParser(prog="trident-web",
                                description="TRIDENT web bridge (offline engine + static UI)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--frontend", default=str(_DEFAULT_FRONTEND),
                   help="Path to the frontend HTML file to serve at /")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    BUS.install()  # fan engine logs out to the web terminal's /api/logstream

    TridentHandler.frontend_path = Path(args.frontend).resolve()

    # Warm the catalog once up-front so the first request is fast and any catalog
    # error surfaces at startup, not mid-demo.
    h = engine.health()
    log.info("catalog loaded: %s techniques, %s packages", h["techniques"], h["packages"])
    log.info("engine=%s  foundry=%s  pyrit=%s  sdk=%s", h["engine"],
             h["foundry_configured"], h["pyrit_installed"], h["sdk_installed"])
    log.info("frontend: %s", TridentHandler.frontend_path)

    httpd = ThreadingHTTPServer((args.host, args.port), TridentHandler)
    url = f"http://{args.host}:{args.port}/"
    log.info("TRIDENT web bridge listening on %s  (Ctrl-C to stop)", url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main(sys.argv[1:])
