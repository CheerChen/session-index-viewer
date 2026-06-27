#!/usr/bin/env python3
"""Local session index server for Claude Code / Codex sessions.

Serves the viewer HTML at / and a live session index at /api/sessions.
Sessions are parsed on demand with an in-memory cache keyed by
(path, mtime, size), so repeat requests only re-parse changed files.

Stdlib only. Binds 127.0.0.1 — session transcripts must never be
exposed beyond this machine.
"""

import glob
import json
import os
import re
import shlex
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 7333
BIND = "127.0.0.1"

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(ROOT, "sessions-index.html")
FAVICON_PATH = os.path.join(ROOT, "favicon.svg")

CLAUDE_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
CODEX_GLOB = os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl")

DEVIN_DB = os.path.expanduser("~/.local/share/devin/cli/sessions.db")

# Sessions synced across machines (e.g. via syncthing) keep the cwd
# they were recorded with. host_for() infers a label from the home-dir
# prefix: cwds under /Users/<name>/ or /home/<name>/ are labelled with
# that <name>, including this machine's own home.
LOCAL_HOME = os.path.expanduser("~")
HOME_DIR_RE = re.compile(r"^/(?:Users|home)/([^/]+)")
LOCAL_USER = os.path.basename(LOCAL_HOME.rstrip("/")) or "unknown"
CURRENT_CWD = os.getcwd() if os.path.isdir(os.getcwd()) else LOCAL_HOME

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
CLIP_LEN = 360

# Files larger than this are read head + tail only; smaller ones whole.
FULL_READ_LIMIT = 2 * 1024 * 1024
HEAD_BYTES = 512 * 1024
TAIL_BYTES = 1024 * 1024

# User texts that are harness/CLI noise, not something the human typed.
SKIP_USER_PREFIXES = (
    "Caveat:",
    "<command-",
    "<local-command",
    "<system-reminder",
    "<user-prompt-submit-hook",
    "<environment_context>",
    "<turn_aborted>",
)

SESSION_ID_RE = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{6,62}[0-9a-fA-F]$")

# Devin CLI session IDs are memorable word-pair slugs (e.g. "foamy-package").
DEVIN_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,62}$")

_cache = {}
_cache_lock = threading.Lock()


def clean_inline(text):
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def clean_multiline(text):
    text = text.replace("\r", "")
    text = re.sub(r"\t+", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n +", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def clip(text, limit=CLIP_LEN):
    return text[:limit] + "..." if len(text) > limit else text


def usable_user_text(text):
    text = text.strip()
    return bool(text) and not text.startswith(SKIP_USER_PREFIXES)


def read_lines(path, size):
    """Return (lines, windowed). Windowed reads cover head + tail only;
    callers must fall back to a full read when fields come up missing."""
    if size <= FULL_READ_LIMIT or HEAD_BYTES + TAIL_BYTES >= size:
        with open(path, "rb") as f:
            data = f.read()
        return data.decode("utf-8", "replace").splitlines(), False

    with open(path, "rb") as f:
        head = f.read(HEAD_BYTES)
        f.seek(size - TAIL_BYTES)
        tail = f.read()

    head_lines = head.decode("utf-8", "replace").splitlines()
    if not head.endswith(b"\n") and head_lines:
        head_lines.pop()  # drop the line cut by the window edge
    tail_text = tail.decode("utf-8", "replace")
    newline = tail_text.find("\n")
    tail_lines = tail_text[newline + 1:].splitlines() if newline != -1 else []
    return head_lines + tail_lines, True


def decode_records(lines):
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def blocks_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def claude_user_text(record):
    content = (record.get("message") or {}).get("content")
    return content if isinstance(content, str) else ""


def parse_claude(records):
    first_user = ""
    title = ""
    cwd = ""
    session_id = ""
    for record in records:
        rtype = record.get("type")
        if rtype == "summary" and record.get("summary"):
            title = record["summary"]
        if not cwd and record.get("cwd"):
            cwd = record["cwd"]
        if not session_id and record.get("sessionId"):
            session_id = record["sessionId"]
        if not first_user and rtype == "user":
            text = claude_user_text(record)
            if usable_user_text(text):
                first_user = text

    last_user = ""
    last_assistant = None
    last_ts = ""
    for record in reversed(records):
        if not last_ts and record.get("timestamp"):
            last_ts = record["timestamp"]
        rtype = record.get("type")
        if last_assistant is None and rtype == "assistant":
            text = blocks_text((record.get("message") or {}).get("content"))
            if text.strip():
                last_assistant = (record, text)
        if not last_user and rtype == "user":
            text = claude_user_text(record)
            if usable_user_text(text):
                last_user = text
        if last_assistant and last_user and last_ts:
            break

    if last_assistant is None:
        return None
    record, assistant_text = last_assistant
    cwd = cwd or record.get("cwd", "")
    session_id = session_id or record.get("sessionId", "")
    sort_ts = last_ts or record.get("timestamp", "")
    if not sort_ts or not session_id:
        return None
    return {
        "source": "claude",
        "sort_ts": sort_ts,
        "cwd": cwd,
        "session_id": session_id,
        "title": title,
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": assistant_text,
    }


def codex_message_text(record, role, content_type):
    payload = record.get("payload") or {}
    if (
        record.get("type") != "response_item"
        or payload.get("type") != "message"
        or payload.get("role") != role
    ):
        return None
    content = payload.get("content") or []
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == content_type
    )


def parse_codex(records):
    meta = next(
        (r.get("payload") or {} for r in records if r.get("type") == "session_meta"),
        {},
    )

    first_user = ""
    for record in records:
        text = codex_message_text(record, "user", "input_text")
        if text and usable_user_text(text):
            first_user = text
            break

    last_user = ""
    last_assistant = ""
    last_ts = ""
    for record in reversed(records):
        if not last_ts and record.get("timestamp"):
            last_ts = record["timestamp"]
        if not last_assistant:
            text = codex_message_text(record, "assistant", "output_text")
            if text and text.strip():
                last_assistant = text
        if not last_user:
            text = codex_message_text(record, "user", "input_text")
            if text and usable_user_text(text):
                last_user = text
        if last_ts and last_user and last_assistant:
            break

    sort_ts = last_ts or meta.get("timestamp", "")
    session_id = meta.get("id", "")
    if not sort_ts or not session_id:
        return None
    return {
        "source": "codex",
        "sort_ts": sort_ts,
        "cwd": meta.get("cwd", ""),
        "session_id": session_id,
        "title": "",
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": last_assistant,
    }


def parse_file(path, source, size):
    lines, windowed = read_lines(path, size)
    parser = parse_claude if source == "claude" else parse_codex
    entry = parser(decode_records(lines))
    if windowed and (entry is None or not entry["first_user"] or not entry["last_user"]):
        # A needed record may sit in the gap between head and tail.
        with open(path, "rb") as f:
            lines = f.read().decode("utf-8", "replace").splitlines()
        entry = parser(decode_records(lines))
    if entry is None:
        return None
    entry["title"] = clip(clean_inline(entry["title"]), 200)
    entry["first_user"] = clip(clean_inline(entry["first_user"]))
    entry["last_user"] = clip(clean_inline(entry["last_user"]))
    entry["last_assistant"] = clean_multiline(entry["last_assistant"])
    return entry


def cached_entry(path, source):
    try:
        st = os.stat(path)
    except OSError:
        return None
    hit = _cache.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    try:
        entry = parse_file(path, source, st.st_size)
    except OSError:
        entry = None
    _cache[path] = (st.st_mtime_ns, st.st_size, entry)
    return entry


def devin_sessions(limit):
    """Query the Devin CLI SQLite database for non-hidden sessions and
    extract conversation snippets directly from the message_nodes table.

    Devin CLI stores session metadata in `sessions` and the full
    conversation in `message_nodes` (one JSON row per chat message).
    ATIF transcript files under transcripts/ are only written when the
    user opts into --export, so relying on them would miss most
    sessions. Reading from the DB instead captures every session.

    Returns a list of entry dicts (same shape as parse_claude/parse_codex).
    Opens read-only so a running devin process is never blocked. If the
    database is absent (devin-cli not installed) or unreadable, returns [].
    """
    if not os.path.isfile(DEVIN_DB):
        return []
    entries = []
    try:
        conn = sqlite3.connect(f"file:{DEVIN_DB}?mode=ro", uri=True)
        sessions = conn.execute(
            "SELECT id, working_directory, title, last_activity_at "
            "FROM sessions WHERE hidden = 0 "
            "ORDER BY last_activity_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        for sid, cwd, title, last_activity_at in sessions:
            cache_key = f"devin:{sid}"
            hit = _cache.get(cache_key)
            if hit and hit[0] == last_activity_at:
                entries.append(hit[1])
                continue

            first_user = ""
            row = conn.execute(
                "SELECT json_extract(chat_message, '$.content') "
                "FROM message_nodes "
                "WHERE session_id = ? "
                "  AND json_extract(chat_message, '$.role') = 'user' "
                "  AND json_extract(chat_message, '$.metadata.is_user_input') = 1 "
                "ORDER BY node_id LIMIT 1",
                (sid,),
            ).fetchone()
            if row and row[0]:
                text = row[0].strip()
                if text and usable_user_text(text):
                    first_user = text

            last_user = ""
            row = conn.execute(
                "SELECT json_extract(chat_message, '$.content') "
                "FROM message_nodes "
                "WHERE session_id = ? "
                "  AND json_extract(chat_message, '$.role') = 'user' "
                "  AND json_extract(chat_message, '$.metadata.is_user_input') = 1 "
                "ORDER BY node_id DESC LIMIT 1",
                (sid,),
            ).fetchone()
            if row and row[0]:
                text = row[0].strip()
                if text and usable_user_text(text):
                    last_user = text

            last_assistant = ""
            row = conn.execute(
                "SELECT json_extract(chat_message, '$.content') "
                "FROM message_nodes "
                "WHERE session_id = ? "
                "  AND json_extract(chat_message, '$.role') = 'assistant' "
                "  AND json_extract(chat_message, '$.content') != '' "
                "ORDER BY node_id DESC LIMIT 1",
                (sid,),
            ).fetchone()
            if row and row[0]:
                last_assistant = row[0].strip()

            if not last_assistant:
                continue  # skip sessions with no agent output yet

            entry = {
                "source": "devin",
                "sort_ts": datetime.fromtimestamp(
                    last_activity_at, tz=timezone.utc
                ).isoformat(),
                "cwd": cwd or "",
                "session_id": sid,
                "title": clip(clean_inline(title or ""), 200),
                "first_user": clip(clean_inline(first_user)),
                "last_user": clip(clean_inline(last_user)),
                "last_assistant": clean_multiline(last_assistant),
            }
            _cache[cache_key] = (last_activity_at, entry)
            entries.append(entry)

        conn.close()
    except sqlite3.Error:
        return []
    return entries


def host_for(cwd):
    if not cwd:
        return LOCAL_USER
    if cwd == LOCAL_HOME or cwd.startswith(LOCAL_HOME + "/"):
        return LOCAL_USER
    match = HOME_DIR_RE.match(cwd)
    if match:
        return match.group(1)
    return LOCAL_USER


def resolve_resume_cwd(cwd):
    """Map a recorded session cwd to something usable on this machine."""
    cwd = (cwd or "").strip()
    if cwd and os.path.isdir(cwd):
        return cwd

    match = HOME_DIR_RE.match(cwd)
    if match:
        suffix = cwd[match.end():].lstrip("/")
        candidate = os.path.join(LOCAL_HOME, suffix) if suffix else LOCAL_HOME
        if os.path.isdir(candidate):
            return candidate

    return CURRENT_CWD


def resume_command(source, session_id, cwd):
    if source == "devin":
        base = f"devin -r {session_id}"
    elif source == "claude":
        base = f"claude --resume {session_id}"
    else:
        base = f"codex resume {session_id}"
    resolved_cwd = resolve_resume_cwd(cwd)
    return f"cd {shlex.quote(resolved_cwd)} && {base}" if resolved_cwd else base


def scan_sessions(limit):
    candidates = []
    for path in glob.glob(CLAUDE_GLOB):
        candidates.append((path, "claude"))
    for path in glob.glob(CODEX_GLOB):
        candidates.append((path, "codex"))

    stats = []
    for path, source in candidates:
        try:
            stats.append((os.stat(path).st_mtime, path, source))
        except OSError:
            continue
    stats.sort(reverse=True)

    with _cache_lock:
        items = []
        seen = set()
        for _, path, source in stats[:limit]:
            entry = cached_entry(path, source)
            if entry is None:
                continue
            key = f"{entry['source']}|{entry['session_id']}"
            if key in seen:
                continue  # syncthing conflict copies of the same session
            seen.add(key)
            items.append(entry)

        # Devin CLI sessions: metadata and conversation text both come
        # straight from the SQLite database (message_nodes table). Kept
        # separate from the glob path because the candidate list comes
        # from a DB query, not a filesystem glob.
        for entry in devin_sessions(limit):
            key = f"devin|{entry['session_id']}"
            if key in seen:
                continue
            seen.add(key)
            items.append(entry)

    items.sort(key=lambda e: e["sort_ts"], reverse=True)
    items = items[:limit]
    return [
        {
            "source": e["source"],
            "host": host_for(e["cwd"]),
            "timestamp": e["sort_ts"],
            "cwd": e["cwd"],
            "session_id": e["session_id"],
            "title": e["title"],
            "first_user": e["first_user"],
            "last_user": e["last_user"],
            "last_assistant": e["last_assistant"],
            "resume_command": resume_command(e["source"], e["session_id"], e["cwd"]),
        }
        for e in items
    ]


# Terminal app to use. "auto" prefers Ghostty > iTerm > Terminal based on
# what's installed. Override by setting to "Ghostty", "iTerm", or "Terminal".
TERMINAL_APP = "auto"


def detect_terminal():
    if TERMINAL_APP != "auto":
        return TERMINAL_APP
    for app in ("Ghostty", "iTerm"):
        if os.path.isdir(f"/Applications/{app}.app"):
            return app
    return "Terminal"


def open_in_terminal(command):
    app = detect_terminal()
    if app == "Ghostty":
        # On macOS the `ghostty` CLI can't launch the app directly; use
        # `open -na` with --args -e. Ghostty's -e expects argv with no
        # shell interpretation, so wrap in `zsh -l -c` to handle `&&`,
        # PATH, and aliases from the user's shell config.
        subprocess.Popen([
            "open", "-na", "Ghostty.app",
            "--args", "-e", "zsh", "-l", "-c", command,
        ])
        return

    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    if app == "iTerm":
        script = (
            'tell application "iTerm"\n'
            '  create window with default profile\n'
            '  tell current session of current window\n'
            f'    write text "{escaped}"\n'
            '  end tell\n'
            'end tell'
        )
    else:
        # Terminal.app — `do script` first creates the window with the
        # command; the leading `activate` from earlier versions spawned an
        # extra empty window before `do script` ran.
        script = (
            'tell application "Terminal"\n'
            f'  do script "{escaped}"\n'
            '  activate\n'
            'end tell'
        )
    subprocess.Popen(["osascript", "-e", script])


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

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            try:
                with open(HTML_PATH, "rb") as f:
                    body = f.read()
            except OSError:
                self.send_error(500, "sessions-index.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/favicon.svg":
            try:
                with open(FAVICON_PATH, "rb") as f:
                    body = f.read()
            except OSError:
                self.send_error(404, "favicon.svg not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/sessions":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", [DEFAULT_LIMIT])[0])
            except ValueError:
                limit = DEFAULT_LIMIT
            limit = max(1, min(limit, MAX_LIMIT))
            self._send_json(scan_sessions(limit))
        else:
            self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/resume":
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

        source = payload.get("source")
        session_id = payload.get("session_id", "")
        cwd = payload.get("cwd", "")
        # Rebuild the command server-side from validated parts; never run
        # a client-supplied string.
        if source not in ("claude", "codex", "devin"):
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


if __name__ == "__main__":
    main()
