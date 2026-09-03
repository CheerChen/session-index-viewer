"""HTTP server: static viewer + /api/sessions + /api/resume."""

import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import (
    BIND,
    DEFAULT_LIMIT,
    DEVIN_ID_RE,
    DIST_PATH,
    FAVICON_PATH,
    INDEX_HTML,
    LEGACY_HTML,
    MAX_LIMIT,
    PORT,
    RESUME_SOURCES,
    SESSION_ID_RE,
)
from .resume import open_in_terminal, resume_command
from .scan import scan_sessions
from .sources import devin


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _origin_allowed(self):
        # Browsers can fire cross-origin POSTs at localhost; only accept
        # requests from our own page (or non-browser clients like curl).
        origin = self.headers.get("Origin")
        return origin is None or origin in (
            f"http://localhost:{PORT}",
            f"http://127.0.0.1:{PORT}",
        )

    def _serve_file(self, path, content_type, cache="no-store"):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self.send_error(404, f"{os.path.basename(path)} not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            html = INDEX_HTML if os.path.isfile(INDEX_HTML) else LEGACY_HTML
            self._serve_file(html, "text/html; charset=utf-8")
        elif path == "/favicon.svg":
            self._serve_file(
                FAVICON_PATH, "image/svg+xml", "public, max-age=3600"
            )
        elif path.startswith("/api/"):
            if path == "/api/sessions":
                query = parse_qs(parsed.query)
                try:
                    limit = int(query.get("limit", [DEFAULT_LIMIT])[0])
                except ValueError:
                    limit = DEFAULT_LIMIT
                limit = max(1, min(limit, MAX_LIMIT))
                self._send_json(scan_sessions(limit))
            elif path == "/api/session":
                query = parse_qs(parsed.query)
                source = query.get("source", [""])[0]
                session_id = query.get("session_id", [""])[0]
                try:
                    page = int(query.get("page", ["1"])[0])
                except ValueError:
                    page = 1
                try:
                    page_size = int(query.get("page_size", ["50"])[0])
                except ValueError:
                    page_size = 50
                page = max(1, page)
                page_size = max(1, min(page_size, 200))
                if source == "devin" and DEVIN_ID_RE.match(session_id):
                    payload = devin.messages(session_id, page, page_size)
                    if payload is None:
                        self.send_error(404)
                    else:
                        self._send_json(
                            {"source": source, "session_id": session_id, **payload}
                        )
                else:
                    self.send_error(404)
            else:
                self.send_error(404)
        else:
            # Static assets from the Vite build (JS/CSS chunks). Serve
            # them from dist/ with long cache; anything else falls back
            # to the SPA index so client-side routing works.
            asset = os.path.join(DIST_PATH, path.lstrip("/"))
            if os.path.isfile(asset):
                guessed = mimetypes.guess_type(asset)[0] or "application/octet-stream"
                self._serve_file(asset, guessed, "public, max-age=31536000, immutable")
            else:
                html = INDEX_HTML if os.path.isfile(INDEX_HTML) else LEGACY_HTML
                self._serve_file(html, "text/html; charset=utf-8")

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/resume", "/api/session/delete"):
            self.send_error(404)
            return
        if not self._origin_allowed():
            self._send_json({"ok": False, "error": "origin not allowed"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, TypeError):
            self._send_json({"ok": False, "error": "invalid JSON body"}, 400)
            return
        if not isinstance(payload, dict):
            self._send_json({"ok": False, "error": "invalid JSON body"}, 400)
            return

        source = payload.get("source")
        session_id = payload.get("session_id", "")
        if path == "/api/session/delete":
            confirmation = payload.get("confirm_session_id", "")
            if source != "devin":
                self._send_json({"ok": False, "error": "unsupported source"}, 400)
                return
            if not isinstance(session_id, str) or not DEVIN_ID_RE.fullmatch(
                session_id
            ):
                self._send_json({"ok": False, "error": "bad session id"}, 400)
                return
            if confirmation != session_id:
                self._send_json({"ok": False, "error": "confirmation mismatch"}, 400)
                return
            result, status = devin.delete_session(session_id)
            self._send_json(result, status)
            return

        cwd = payload.get("cwd", "")
        # Rebuild the command server-side from validated parts; never run
        # a client-supplied string.
        if source not in RESUME_SOURCES:
            self._send_json({"ok": False, "error": "unknown source"}, 400)
            return
        id_re = DEVIN_ID_RE if source == "devin" else SESSION_ID_RE
        if not id_re.match(session_id):
            self._send_json({"ok": False, "error": "bad session id"}, 400)
            return
        open_in_terminal(resume_command(source, session_id, cwd))
        self._send_json({"ok": True})

    def log_message(self, fmt, *args):
        pass  # keep launchd logs quiet on routine requests


def main():
    # Warm the cache so the first browser hit doesn't eat the cold scan.
    threading.Thread(target=scan_sessions, args=(DEFAULT_LIMIT,), daemon=True).start()
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"session-index-viewer listening on http://{BIND}:{PORT}")
    server.serve_forever()
