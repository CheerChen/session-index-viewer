"""opencode sessions from ~/.local/share/opencode/opencode.db.

opencode stores each session's metadata (title, directory, cumulative
token sums, model) on a denormalised `session` row, and the conversation
as `message` rows (role) fanned out into `part` rows (type text / tool /
reasoning / step-*). Visible text lives in text parts, so first/last user
and last assistant come from joining parts to their message role.

Read-only, no file globbing — same collect() contract as Devin/Copilot.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

from .. import cache
from ..config import OPENCODE_DB
from ..text import clean_inline, clean_multiline, clip, usable_user_text
from ..trash import delete_db_session


def _iso(ms):
    if not ms:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return ""


def _model_id(raw):
    """session.model is a JSON blob like {"id":"...","providerID":"..."}."""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if isinstance(data, dict):
        return data.get("id") or ""
    return ""


def _text_part(conn, sid, role, newest):
    order = "DESC" if newest else "ASC"
    row = conn.execute(
        "SELECT json_extract(p.data, '$.text') "
        "FROM part p JOIN message m ON p.message_id = m.id "
        "WHERE p.session_id = ? "
        "  AND json_extract(p.data, '$.type') = 'text' "
        "  AND json_extract(m.data, '$.role') = ? "
        f"ORDER BY p.time_created {order} LIMIT 1",
        (sid, role),
    ).fetchone()
    return (row[0] or "").strip() if row and row[0] else ""


def collect(limit):
    if not os.path.isfile(OPENCODE_DB):
        return []
    entries = []
    try:
        conn = sqlite3.connect(f"file:{OPENCODE_DB}?mode=ro", uri=True)
        sessions = conn.execute(
            "SELECT id, directory, title, time_created, time_updated, "
            "  tokens_input, tokens_output, tokens_reasoning, "
            "  tokens_cache_read, tokens_cache_write, model "
            "FROM session ORDER BY time_updated DESC LIMIT ?",
            (limit,),
        ).fetchall()

        # peak context = largest single assistant-message total; tool_calls
        # = tool parts; user_turns = user messages. One grouped query each.
        peak_by_sid = {}
        tools_by_sid = {}
        turns_by_sid = {}
        msgs_by_sid = {}
        if sessions:
            placeholders = ",".join("?" for _ in sessions)
            sids = [s[0] for s in sessions]
            for sid, peak in conn.execute(
                "SELECT session_id, "
                "  MAX(COALESCE(json_extract(data,'$.tokens.total'),0)) "
                f"FROM message WHERE session_id IN ({placeholders}) "
                "GROUP BY session_id",
                sids,
            ).fetchall():
                peak_by_sid[sid] = int(peak or 0)
            for sid, n in conn.execute(
                "SELECT session_id, COUNT(*) "
                f"FROM part WHERE session_id IN ({placeholders}) "
                "  AND json_extract(data,'$.type') = 'tool' "
                "GROUP BY session_id",
                sids,
            ).fetchall():
                tools_by_sid[sid] = int(n or 0)
            for sid, role, n in conn.execute(
                "SELECT session_id, json_extract(data,'$.role'), COUNT(*) "
                f"FROM message WHERE session_id IN ({placeholders}) "
                "GROUP BY session_id, json_extract(data,'$.role')",
                sids,
            ).fetchall():
                msgs_by_sid[sid] = msgs_by_sid.get(sid, 0) + int(n or 0)
                if role == "user":
                    turns_by_sid[sid] = int(n or 0)

        for (
            sid,
            directory,
            title,
            time_created,
            time_updated,
            t_in,
            t_out,
            t_reason,
            t_cr,
            t_cw,
            model,
        ) in sessions:
            cache_key = f"opencode:{sid}"
            hit = cache.get(cache_key)
            if hit and hit[0] == time_updated:
                if hit[1] is not None:
                    entries.append(hit[1])
                continue

            last_assistant = _text_part(conn, sid, "assistant", newest=True)
            if not last_assistant:
                cache.set(cache_key, (time_updated, None))
                continue
            first_user = _text_part(conn, sid, "user", newest=False)
            last_user = _text_part(conn, sid, "user", newest=True)
            if first_user and not usable_user_text(first_user):
                first_user = ""
            if last_user and not usable_user_text(last_user):
                last_user = ""

            usage = {
                "input_tokens": int(t_in or 0),
                "output_tokens": int(t_out or 0) + int(t_reason or 0),
                "cache_read_tokens": int(t_cr or 0),
                "cache_creation_tokens": int(t_cw or 0),
                "tool_calls": tools_by_sid.get(sid, 0),
                "user_turns": turns_by_sid.get(sid, 0),
                "messages": msgs_by_sid.get(sid, 0),
                "peak_context_tokens": peak_by_sid.get(sid, 0),
                "duration_s": max(0, int(((time_updated or 0) - (time_created or 0)) / 1000)),
                "model": _model_id(model),
            }

            entry = {
                "source": "opencode",
                "sort_ts": _iso(time_updated) or _iso(time_created),
                "cwd": directory or "",
                "session_id": sid,
                "title": clip(clean_inline(title or ""), 200),
                "first_user": clip(clean_inline(first_user)),
                "last_user": clip(clean_inline(last_user)),
                "last_assistant": clean_multiline(last_assistant),
                "usage": usage,
            }
            if not entry["sort_ts"]:
                continue
            cache.set(cache_key, (time_updated, entry))
            entries.append(entry)

        conn.close()
    except sqlite3.Error:
        return []
    return entries


def delete_session(session_id):
    """Archive the session's rows to Trash, then delete them from the DB."""
    result, status = delete_db_session(
        OPENCODE_DB, "session", session_id, "opencode"
    )
    if result.get("ok"):
        cache.delete(f"opencode:{session_id}")
    return result, status
