"""Grok Build TUI sessions under ~/.grok/sessions."""

import json
import os
import re
from datetime import datetime

from .. import cache
from ..config import SESSION_ID_RE
from ..text import blocks_text, clean_inline, clean_multiline, clip, usable_user_text
from ..trash import move_to_trash


def sessions_root():
    home = os.environ.get("GROK_HOME") or os.path.expanduser("~/.grok")
    return os.path.join(os.path.expanduser(home), "sessions")


def user_text_from_content(content):
    """Pull displayable user text from a chat_history content field."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        text = "\n".join(parts)
    else:
        return ""
    # Real human prompts are wrapped in <user_query>; strip harness noise.
    match = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if usable_user_text(text) and not text.lstrip().startswith(
        ("<user_info>", "<system-reminder>", "<git_status>")
    ):
        return text.strip()
    return ""


def parse_updates(path):
    """Extract first/last user and last assistant from updates.jsonl.

    updates.jsonl is the ACP session/update stream. user_message_chunk
    holds clean human input; agent_message_chunk is the visible reply.
    """
    first_user = ""
    last_user = ""
    assistant_buf = []
    last_assistant = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                update = ((record.get("params") or {}).get("update")) or {}
                kind = update.get("sessionUpdate")
                if kind == "user_message_chunk":
                    if assistant_buf:
                        last_assistant = "".join(assistant_buf)
                        assistant_buf = []
                    content = update.get("content") or {}
                    text = content.get("text") if isinstance(content, dict) else ""
                    if text and usable_user_text(text):
                        if not first_user:
                            first_user = text
                        last_user = text
                elif kind == "agent_message_chunk":
                    content = update.get("content") or {}
                    text = content.get("text") if isinstance(content, dict) else ""
                    if text:
                        assistant_buf.append(text)
    except OSError:
        return first_user, last_user, last_assistant
    if assistant_buf:
        last_assistant = "".join(assistant_buf)
    return first_user, last_user, last_assistant


def parse_chat_history(path):
    """Fallback when updates.jsonl is missing or empty."""
    first_user = ""
    last_user = ""
    last_assistant = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                rtype = record.get("type")
                if rtype == "user":
                    if record.get("synthetic_reason"):
                        continue
                    text = user_text_from_content(record.get("content"))
                    if text and usable_user_text(text):
                        if not first_user:
                            first_user = text
                        last_user = text
                elif rtype == "assistant":
                    text = blocks_text(record.get("content"))
                    if text and text.strip():
                        last_assistant = text
    except OSError:
        pass
    return first_user, last_user, last_assistant


def is_non_interactive(session_dir):
    """True for headless one-shots (`grok -p` / --single).

    prompt_context.json records is_non_interactive for the session's
    prompt harness. Interactive TUI sessions set it false; CLI single-turn
    probes (e.g. resume smoke tests) set it true and usually have no
    generated_title — they clutter the index without being useful to resume.
    """
    path = os.path.join(session_dir, "prompt_context.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            ctx = json.load(f)
    except (OSError, ValueError, TypeError):
        return False
    return bool(ctx.get("is_non_interactive"))


def parse_usage(session_dir, summary, sort_ts):
    """Map Grok signals.json (+ summary fallbacks) into the shared usage shape.

    Grok does not persist lifetime input/output token sums on disk. The
    best available figures live in signals.json:
      contextTokensUsed   — tokens currently in the context window
      toolCallCount       — tool invocations
      userMessageCount / turnCount — user turns
      sessionDurationSeconds, primaryModelId
    We place contextTokensUsed in both input_tokens (so the one-line
    summary is non-zero) and peak_context_tokens (closest thing to peak
    context occupancy). Cache fields stay 0 — not recorded separately.
    """
    signals = {}
    path = os.path.join(session_dir, "signals.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                signals = json.load(f) or {}
        except (OSError, ValueError, TypeError):
            signals = {}

    context_used = int(signals.get("contextTokensUsed") or 0)
    tool_calls = int(signals.get("toolCallCount") or 0)
    user_turns = int(
        signals.get("userMessageCount") or signals.get("turnCount") or 0
    )
    messages = int(signals.get("assistantMessageCount") or 0) + int(
        signals.get("userMessageCount") or 0
    )
    if not messages:
        messages = int(summary.get("num_messages") or 0)
    model = (
        signals.get("primaryModelId") or summary.get("current_model_id") or ""
    )
    duration_s = int(signals.get("sessionDurationSeconds") or 0)
    if not duration_s:
        created = summary.get("created_at") or ""
        if created and sort_ts:
            try:
                c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                u = datetime.fromisoformat(sort_ts.replace("Z", "+00:00"))
                duration_s = max(0, int((u - c).total_seconds()))
            except ValueError:
                pass

    if not (context_used or tool_calls or user_turns or messages or model):
        return None
    return {
        "input_tokens": context_used,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "tool_calls": tool_calls,
        "user_turns": user_turns,
        "messages": messages,
        "peak_context_tokens": context_used,
        "duration_s": duration_s,
        "model": model,
    }


def parse_session(session_dir):
    """Build a session entry from a Grok session directory, or None."""
    summary_path = os.path.join(session_dir, "summary.json")
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except (OSError, ValueError, TypeError):
        return None

    info = summary.get("info") or {}
    session_id = info.get("id") or os.path.basename(session_dir.rstrip("/"))
    cwd = info.get("cwd") or ""
    sort_ts = (
        summary.get("last_active_at")
        or summary.get("updated_at")
        or summary.get("created_at")
        or ""
    )
    title = summary.get("generated_title") or summary.get("session_summary") or ""
    if not sort_ts or not session_id:
        return None
    if not SESSION_ID_RE.match(session_id):
        return None
    # Skip headless/system-style one-shots so they don't appear as empty
    # "Opening prompt: RESUME_OK" style cards next to real TUI work.
    if is_non_interactive(session_dir):
        return None

    updates_path = os.path.join(session_dir, "updates.jsonl")
    chat_path = os.path.join(session_dir, "chat_history.jsonl")
    first_user, last_user, last_assistant = "", "", ""
    if os.path.isfile(updates_path):
        first_user, last_user, last_assistant = parse_updates(updates_path)
    if not last_assistant and os.path.isfile(chat_path):
        fu, lu, la = parse_chat_history(chat_path)
        first_user = first_user or fu
        last_user = last_user or lu
        last_assistant = la
    if not last_assistant:
        return None  # empty / not-yet-started sessions

    usage = parse_usage(session_dir, summary, sort_ts)

    return {
        "source": "grok",
        "sort_ts": sort_ts,
        "cwd": cwd,
        "session_id": session_id,
        "title": clip(clean_inline(title), 200),
        "first_user": clip(clean_inline(first_user)),
        "last_user": clip(clean_inline(last_user)),
        "last_assistant": clean_multiline(last_assistant),
        "usage": usage,
    }


def collect(limit):
    """Scan ~/.grok/sessions for session directories with a summary.json.

    Layout: sessions/<encoded-cwd>/<session-id>/summary.json
    session_search.sqlite at the sessions root is a derived FTS index
    and is intentionally ignored.
    """
    root = sessions_root()
    if not os.path.isdir(root):
        return []

    summaries = []
    try:
        for group in os.listdir(root):
            group_path = os.path.join(root, group)
            if not os.path.isdir(group_path):
                continue
            # Skip non-group files/dirs (e.g. nothing under root except
            # encoded cwd folders and the sqlite index file).
            try:
                for sid in os.listdir(group_path):
                    session_dir = os.path.join(group_path, sid)
                    summary_path = os.path.join(session_dir, "summary.json")
                    if not os.path.isfile(summary_path):
                        continue
                    try:
                        mtime = os.stat(summary_path).st_mtime
                    except OSError:
                        continue
                    summaries.append((mtime, session_dir, summary_path))
            except OSError:
                continue
    except OSError:
        return []

    summaries.sort(reverse=True)
    entries = []
    for _, session_dir, summary_path in summaries[: max(limit * 2, limit)]:
        # Cache key covers summary + updates + signals so new turns
        # and usage counter bumps both invalidate.
        updates_path = os.path.join(session_dir, "updates.jsonl")
        signals_path = os.path.join(session_dir, "signals.json")
        try:
            st = os.stat(summary_path)
            cache_sig = (st.st_mtime_ns, st.st_size)
            if os.path.isfile(updates_path):
                ust = os.stat(updates_path)
                cache_sig = cache_sig + (ust.st_mtime_ns, ust.st_size)
            if os.path.isfile(signals_path):
                sst = os.stat(signals_path)
                cache_sig = cache_sig + (sst.st_mtime_ns, sst.st_size)
        except OSError:
            continue
        cache_key = f"grok:{session_dir}"
        hit = cache.get(cache_key)
        if hit and hit[0] == cache_sig:
            if hit[1] is not None:
                entries.append(hit[1])
            continue
        entry = parse_session(session_dir)
        cache.set(cache_key, (cache_sig, entry))
        if entry is not None:
            entries.append(entry)
        if len(entries) >= limit:
            break
    return entries


def delete_session(session_id):
    """Trash the whole session directory sessions/<cwd>/<id>/."""
    root = sessions_root()
    try:
        groups = os.listdir(root)
    except OSError:
        return {"ok": False, "error": "Session not found."}, 404
    for group in groups:
        session_dir = os.path.join(root, group, session_id)
        summary_path = os.path.join(session_dir, "summary.json")
        if not os.path.isfile(summary_path):
            continue
        # The directory name is the id per the layout; when summary.json
        # also carries one, it must agree before we touch anything.
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                info = (json.load(f) or {}).get("info") or {}
        except (OSError, ValueError, TypeError):
            info = {}
        if info.get("id") and info["id"] != session_id:
            continue
        try:
            move_to_trash(session_dir)
        except OSError:
            return {
                "ok": False,
                "error": "Could not move session to Trash.",
            }, 500
        cache.delete(f"grok:{session_dir}")
        return {"ok": True}, 200
    return {"ok": False, "error": "Session not found."}, 404
