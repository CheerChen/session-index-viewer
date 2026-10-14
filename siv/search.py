"""Full-text search over conversation messages (user prompts and replies).

The index holds exactly what the detail pane shows: each source's
messages() output, one row per folded message, with its position in the
conversation. Rows live in a plain table; an external-content FTS5 table
with the trigram tokenizer indexes them. Trigram matches CJK and code
substrings, but only for terms of 3+ characters, so shorter terms fall
back to LIKE over the same rows.

A session is re-indexed when its list timestamp (last activity) changes;
sessions that left the list are dropped. The first build runs in the
background, and searches during it return what is indexed so far.
"""

import os
import sqlite3
import threading

from .config import INDEX_DB
from .sources import MODULES

# Positions returned per session; enough to count hits and tell which
# pages hold them without shipping every offset of a chatty session.
MAX_POSITIONS = 500
# A search catches up this many changed sessions inline; more than that
# (first build, long downtime) goes to a background thread instead of
# holding the request.
INLINE_SYNC_MAX = 20

_sync_lock = threading.Lock()
_state = {"building": False}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS indexed (
  key TEXT PRIMARY KEY,
  sig TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS msg (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL,
  pos INTEGER NOT NULL,
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS msg_key ON msg(key);
CREATE VIRTUAL TABLE IF NOT EXISTS msg_fts USING fts5(
  body, content='msg', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS msg_ai AFTER INSERT ON msg BEGIN
  INSERT INTO msg_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS msg_ad AFTER DELETE ON msg BEGIN
  INSERT INTO msg_fts(msg_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
"""


def _connect():
    os.makedirs(os.path.dirname(INDEX_DB), exist_ok=True)
    conn = sqlite3.connect(INDEX_DB, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _key(source, session_id):
    return f"{source}|{session_id}"


def _all_messages(source, session_id):
    module = MODULES.get(source)
    if module is None:
        return []
    page = module.messages(session_id, 1, 1_000_000)
    return page["messages"] if page else []


def sync(sessions):
    """Bring the index in line with the session list (scan_sessions output).

    Returns False without doing anything when another sync is running.
    """
    if not _sync_lock.acquire(blocking=False):
        return False
    try:
        conn = _connect()
        try:
            indexed = dict(conn.execute("SELECT key, sig FROM indexed"))
            wanted = {
                _key(s["source"], s["session_id"]): s for s in sessions
            }
            pending = [
                k for k, s in wanted.items() if indexed.get(k) != s["timestamp"]
            ]
            _state["building"] = len(pending) > INLINE_SYNC_MAX
            for key in indexed.keys() - wanted.keys():
                with conn:
                    conn.execute("DELETE FROM msg WHERE key = ?", (key,))
                    conn.execute("DELETE FROM indexed WHERE key = ?", (key,))
            for key in pending:
                s = wanted[key]
                sig = s["timestamp"]
                messages = _all_messages(s["source"], s["session_id"])
                # One transaction per session: readers never see a
                # half-replaced conversation.
                with conn:
                    conn.execute("DELETE FROM msg WHERE key = ?", (key,))
                    conn.executemany(
                        "INSERT INTO msg(key, pos, body) VALUES (?, ?, ?)",
                        [
                            (key, pos, m["content"])
                            for pos, m in enumerate(messages)
                            if m.get("content")
                        ],
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO indexed(key, sig) VALUES (?, ?)",
                        (key, sig),
                    )
        finally:
            conn.close()
    finally:
        _state["building"] = False
        _sync_lock.release()
    return True


def catch_up(sessions):
    """Sync before a search without ever blocking it on a big rebuild."""
    try:
        conn = _connect()
        try:
            indexed = dict(conn.execute("SELECT key, sig FROM indexed"))
        finally:
            conn.close()
    except sqlite3.Error:
        return
    pending = sum(
        1
        for s in sessions
        if indexed.get(_key(s["source"], s["session_id"])) != s["timestamp"]
    )
    if pending <= INLINE_SYNC_MAX:
        sync(sessions)
    else:
        _state["building"] = True
        threading.Thread(target=sync, args=(sessions,), daemon=True).start()


def parse_query(q):
    """Split into terms; "double quotes" keep a phrase together."""
    terms = []
    buf = []
    quoted = False
    for ch in q:
        if ch == '"':
            if quoted and buf:
                terms.append("".join(buf))
                buf = []
            quoted = not quoted
        elif ch.isspace() and not quoted:
            if buf:
                terms.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        terms.append("".join(buf))
    return [t for t in terms if t.strip()]


def _like_escape(term):
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(q):
    """{"hits": {key: {"count", "positions"}}, "terms", "indexing"}.

    Every term must occur in the same message (AND per message). Terms of
    3+ characters go through FTS5; shorter ones are LIKE filters.
    """
    terms = parse_query(q)
    result = {"hits": {}, "terms": terms, "indexing": _state["building"]}
    if not terms:
        return result
    long_terms = [t for t in terms if len(t) >= 3]
    short_terms = [t for t in terms if len(t) < 3]

    where = []
    params = []
    if long_terms:
        match = " AND ".join('"' + t.replace('"', '""') + '"' for t in long_terms)
        where.append("msg.id IN (SELECT rowid FROM msg_fts WHERE msg_fts MATCH ?)")
        params.append(match)
    for t in short_terms:
        where.append("msg.body LIKE ? ESCAPE '\\'")
        params.append(f"%{_like_escape(t)}%")

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT key, pos FROM msg WHERE " + " AND ".join(where) +
            " ORDER BY key, pos",
            params,
        ).fetchall()
    except sqlite3.OperationalError:
        return result
    finally:
        conn.close()

    for key, pos in rows:
        hit = result["hits"].setdefault(key, {"count": 0, "positions": []})
        hit["count"] += 1
        if len(hit["positions"]) < MAX_POSITIONS:
            hit["positions"].append(pos)
    return result
