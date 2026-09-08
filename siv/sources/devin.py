"""Devin CLI sessions from the local SQLite database."""

import json
import math
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

from .. import cache
from ..config import DEVIN_DB
from ..text import clean_inline, clean_multiline, clip, usable_user_text


def collect(limit):
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
            "SELECT id, working_directory, title, last_activity_at, "
            "model, created_at "
            "FROM sessions WHERE hidden = 0 "
            "ORDER BY last_activity_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        # Only sessions whose cached entry is stale (last_activity_at
        # changed) need re-parsing. Aggregating usage over message_nodes
        # is the dominant cost, so restrict it to those sids — a warm
        # request where nothing changed then skips the big scan entirely.
        stale_sids = [
            sid
            for sid, _cwd, _title, last_activity_at, _model, _created in sessions
            if not (
                (hit := cache.get(f"devin:{sid}")) and hit[0] == last_activity_at
            )
        ]

        # Aggregate token / tool / turn usage per session in one query so
        # we don't add N+1 round-trips. Matches the metrics fields Devin
        # CLI writes on every assistant message (see /session-stats).
        # peak_context_tokens = max(input_tokens) over assistant turns,
        # i.e. the largest context window this session ever occupied.
        usage_by_sid = {}
        if stale_sids:
            placeholders = ",".join("?" for _ in stale_sids)
            rows = conn.execute(
                "SELECT session_id, "
                "  SUM(CASE WHEN json_extract(chat_message,'$.metadata.metrics.input_tokens') IS NOT NULL "
                "    THEN json_extract(chat_message,'$.metadata.metrics.input_tokens') ELSE 0 END), "
                "  SUM(CASE WHEN json_extract(chat_message,'$.metadata.metrics.output_tokens') IS NOT NULL "
                "    THEN json_extract(chat_message,'$.metadata.metrics.output_tokens') ELSE 0 END), "
                "  SUM(CASE WHEN json_extract(chat_message,'$.metadata.metrics.cache_read_tokens') IS NOT NULL "
                "    THEN json_extract(chat_message,'$.metadata.metrics.cache_read_tokens') ELSE 0 END), "
                "  SUM(CASE WHEN json_extract(chat_message,'$.metadata.metrics.cache_creation_tokens') IS NOT NULL "
                "    THEN json_extract(chat_message,'$.metadata.metrics.cache_creation_tokens') ELSE 0 END), "
                "  SUM(CASE WHEN json_extract(chat_message,'$.tool_calls') IS NOT NULL "
                "    THEN json_array_length(json_extract(chat_message,'$.tool_calls')) ELSE 0 END), "
                "  SUM(CASE WHEN json_extract(chat_message,'$.role')='user' "
                "    AND json_extract(chat_message,'$.metadata.is_user_input')=1 THEN 1 ELSE 0 END), "
                "  COUNT(*), "
                "  MAX(CASE WHEN json_extract(chat_message,'$.role')='assistant' "
                "    AND json_extract(chat_message,'$.metadata.metrics.input_tokens') IS NOT NULL "
                "    THEN json_extract(chat_message,'$.metadata.metrics.input_tokens') END) "
                f"FROM message_nodes WHERE session_id IN ({placeholders}) "
                "GROUP BY session_id",
                stale_sids,
            ).fetchall()
            for sid, inp, out, cr, cc, tools, turns, msgs, peak in rows:
                usage_by_sid[sid] = {
                    "input_tokens": inp or 0,
                    "output_tokens": out or 0,
                    "cache_read_tokens": cr or 0,
                    "cache_creation_tokens": cc or 0,
                    "tool_calls": tools or 0,
                    "user_turns": turns or 0,
                    "messages": msgs or 0,
                    "peak_context_tokens": peak or 0,
                }

        for sid, cwd, title, last_activity_at, model, created_at in sessions:
            cache_key = f"devin:{sid}"
            hit = cache.get(cache_key)
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

            usage = usage_by_sid.get(sid, {})
            # Wall-clock duration between first and last activity. Sessions
            # span idle time too, so this is an upper bound on active work.
            duration_s = max(0, (last_activity_at or 0) - (created_at or 0))
            usage["duration_s"] = duration_s
            usage["model"] = model or ""

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
                "usage": usage,
            }
            cache.set(cache_key, (last_activity_at, entry))
            entries.append(entry)

        conn.close()
    except sqlite3.Error:
        return []
    return entries


def _message_out(node_id, m):
    """Project one message_nodes row into the API response shape."""
    out = {
        "node_id": node_id,
        "role": m.get("role", ""),
        "content": m.get("content", "") or "",
    }
    metadata = m.get("metadata") or {}
    if metadata.get("created_at"):
        out["created_at"] = metadata["created_at"]
    thinking = m.get("thinking")
    if isinstance(thinking, dict):
        text = thinking.get("thinking")
        if text:
            out["thinking"] = text
    return out


def _has_reply(message):
    content = message.get("content")
    return isinstance(content, str) and bool(content.strip())


def _conversation_messages(rows):
    messages = []
    assistant = None
    for node_id, raw in rows:
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(parsed, dict):
            continue
        message = _message_out(node_id, parsed)
        if message["role"] == "user":
            if assistant and _has_reply(assistant):
                messages.append(assistant)
            assistant = None
            messages.append(message)
            continue
        calls = parsed.get("tool_calls")
        tool_call_count = len(calls) if isinstance(calls, list) else 0
        if assistant is None:
            assistant = message
            assistant["tool_call_count"] = tool_call_count
            continue
        assistant["node_id"] = message["node_id"]
        for key in ("created_at", "content", "thinking"):
            if message.get(key):
                assistant[key] = message[key]
        assistant["tool_call_count"] += tool_call_count
    if assistant and _has_reply(assistant):
        messages.append(assistant)
    return messages


def messages(session_id, page=1, page_size=50):
    """Return user turns and final assistant replies from the active chain.

    System context and tool results are omitted. Assistant events within one
    user turn are combined, with their tool-call count attached to the final
    reply. The caller must validate session_id against DEVIN_ID_RE first.
    Returns None when the DB or session is missing.
    """
    if not os.path.isfile(DEVIN_DB):
        return None
    try:
        conn = sqlite3.connect(f"file:{DEVIN_DB}?mode=ro", uri=True)
        try:
            session = conn.execute(
                "SELECT main_chain_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                return None
            rows = conn.execute(
                "WITH RECURSIVE chain(node_id, parent_node_id, chat_message, depth) AS ("
                "  SELECT node_id, parent_node_id, chat_message, 0 FROM message_nodes "
                "  WHERE session_id = ? AND node_id = ? "
                "  UNION ALL "
                "  SELECT parent.node_id, parent.parent_node_id, "
                "    parent.chat_message, child.depth + 1 "
                "  FROM message_nodes AS parent JOIN chain AS child "
                "    ON parent.session_id = ? "
                "   AND parent.node_id = child.parent_node_id"
                ") "
                "SELECT node_id, chat_message FROM chain "
                "WHERE json_extract(chat_message, '$.role') IN ('user','assistant') "
                "ORDER BY depth DESC",
                (session_id, session[0], session_id),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return None

    all_messages = _conversation_messages(rows)
    total = len(all_messages)
    offset = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 1,
        "messages": all_messages[offset : offset + page_size],
    }


def _executable():
    candidates = (
        shutil.which("devin"),
        os.path.expanduser("~/.local/bin/devin"),
        "/opt/homebrew/bin/devin",
        "/usr/local/bin/devin",
    )
    return next(
        (
            path
            for path in candidates
            if path and os.path.isfile(path) and os.access(path, os.X_OK)
        ),
        None,
    )


def delete_session(session_id):
    if not os.path.isfile(DEVIN_DB):
        return {"ok": False, "error": "Session not found."}, 404
    try:
        conn = sqlite3.connect(f"file:{DEVIN_DB}?mode=ro", uri=True)
        try:
            exists = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return {"ok": False, "error": "Unable to read Devin sessions."}, 500
    if exists is None:
        return {"ok": False, "error": "Session not found."}, 404

    executable = _executable()
    if executable is None:
        return {"ok": False, "error": "Devin CLI was not found."}, 503
    try:
        result = subprocess.run(
            [executable, "rm", "--force", session_id],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Devin session deletion timed out."}, 504
    except OSError:
        return {"ok": False, "error": "Unable to run Devin CLI."}, 503
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".lower()
        if any(word in output for word in ("open", "running", "locked", "in use")):
            return {"ok": False, "error": "Session is currently open in Devin."}, 409
        return {"ok": False, "error": "Devin could not delete this session."}, 500

    cache.delete(f"devin:{session_id}")
    return {"ok": True}, 200
