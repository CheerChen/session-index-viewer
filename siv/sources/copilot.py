"""GitHub Copilot CLI sessions from ~/.copilot/session-store.db.

The Copilot CLI keeps a clean relational store:
  sessions(id, cwd, summary, created_at, updated_at, ...)
  turns(session_id, turn_index, user_message, assistant_response, ...)
  assistant_usage_events(session_id, input_tokens, output_tokens,
    cache_read_tokens, cache_write_tokens, reasoning_tokens, model, ...)

Because `turns` already stores pre-formatted user/assistant text, this
adapter mirrors the Devin one: query the DB read-only and build the shared
entry shape directly (no file globbing).
"""

import os
import sqlite3

from .. import cache
from ..config import COPILOT_DB
from ..text import clean_inline, clean_multiline, clip, usable_user_text
from ..trash import delete_db_session


def collect(limit):
    if not os.path.isfile(COPILOT_DB):
        return []
    entries = []
    try:
        conn = sqlite3.connect(f"file:{COPILOT_DB}?mode=ro", uri=True)
        sessions = conn.execute(
            "SELECT id, cwd, summary, created_at, updated_at "
            "FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        # Aggregate per-turn usage events in one pass. peak_context_tokens
        # = the largest single input_tokens (closest to peak context
        # occupancy); reasoning tokens fold into output like other adapters.
        usage_by_sid = {}
        if sessions:
            placeholders = ",".join("?" for _ in sessions)
            rows = conn.execute(
                "SELECT session_id, "
                "  SUM(COALESCE(input_tokens,0)), "
                "  SUM(COALESCE(output_tokens,0) + COALESCE(reasoning_tokens,0)), "
                "  SUM(COALESCE(cache_read_tokens,0)), "
                "  SUM(COALESCE(cache_write_tokens,0)), "
                "  MAX(COALESCE(input_tokens,0)), "
                "  SUM(COALESCE(duration_ms,0)), "
                "  MAX(model) "
                f"FROM assistant_usage_events WHERE session_id IN ({placeholders}) "
                "GROUP BY session_id",
                [s[0] for s in sessions],
            ).fetchall()
            for sid, inp, out, cr, cw, peak, dur_ms, model in rows:
                usage_by_sid[sid] = {
                    "input_tokens": inp or 0,
                    "output_tokens": out or 0,
                    "cache_read_tokens": cr or 0,
                    "cache_creation_tokens": cw or 0,
                    "tool_calls": 0,
                    "peak_context_tokens": peak or 0,
                    "duration_s": int((dur_ms or 0) / 1000),
                    "model": model or "",
                }

        for sid, cwd, summary, created_at, updated_at in sessions:
            cache_key = f"copilot:{sid}"
            hit = cache.get(cache_key)
            if hit and hit[0] == updated_at:
                if hit[1] is not None:
                    entries.append(hit[1])
                continue

            turns = conn.execute(
                "SELECT user_message, assistant_response FROM turns "
                "WHERE session_id = ? ORDER BY turn_index",
                (sid,),
            ).fetchall()

            first_user = ""
            last_user = ""
            last_assistant = ""
            user_turns = 0
            for user_message, assistant_response in turns:
                if user_message:
                    text = user_message.strip()
                    if text and usable_user_text(text):
                        if not first_user:
                            first_user = text
                        last_user = text
                        user_turns += 1
                if assistant_response and assistant_response.strip():
                    last_assistant = assistant_response.strip()

            if not last_assistant:
                cache.set(cache_key, (updated_at, None))
                continue

            usage = usage_by_sid.get(sid)
            if usage is not None:
                usage["user_turns"] = user_turns
                usage["messages"] = len(turns)

            entry = {
                "source": "copilot",
                "sort_ts": updated_at or created_at or "",
                "cwd": cwd or "",
                "session_id": sid,
                "title": clip(clean_inline(summary or ""), 200),
                "first_user": clip(clean_inline(first_user)),
                "last_user": clip(clean_inline(last_user)),
                "last_assistant": clean_multiline(last_assistant),
                "usage": usage,
            }
            if not entry["sort_ts"]:
                continue
            cache.set(cache_key, (updated_at, entry))
            entries.append(entry)

        conn.close()
    except sqlite3.Error:
        return []
    return entries


def delete_session(session_id):
    """Archive the session's rows to Trash, then delete them from the DB."""
    result, status = delete_db_session(
        COPILOT_DB, "sessions", session_id, "copilot"
    )
    if result.get("ok"):
        cache.delete(f"copilot:{session_id}")
    return result, status
