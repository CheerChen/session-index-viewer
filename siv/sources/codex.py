"""Codex sessions under ~/.codex/sessions."""

from datetime import datetime

from ..config import CODEX_GLOB
from ..text import usable_user_text
from .jsonl_files import collect_jsonl, delete_file_session


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


def _duration_s(first_ts, last_ts):
    if not first_ts or not last_ts:
        return 0
    try:
        a = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        b = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        return max(0, int((b - a).total_seconds()))
    except ValueError:
        return 0


def parse_codex(records):
    meta = next(
        (r.get("payload") or {} for r in records if r.get("type") == "session_meta"),
        {},
    )

    first_user = ""
    first_ts = ""
    last_ts = ""
    model = ""
    # Codex emits cumulative totals on event_msg token_count; keep the
    # last non-null total_token_usage as the session sum.
    total_usage = None
    peak_context_tokens = 0
    tool_calls = 0
    user_turns = 0
    messages = 0

    for record in records:
        ts = record.get("timestamp") or ""
        if ts:
            if not first_ts:
                first_ts = ts
            last_ts = ts
        rtype = record.get("type")
        payload = record.get("payload") or {}

        if rtype == "turn_context" and payload.get("model"):
            model = payload["model"]

        if rtype == "event_msg":
            etype = payload.get("type")
            if etype == "token_count":
                info = payload.get("info") or {}
                tot = info.get("total_token_usage")
                if tot:
                    total_usage = tot
                last = info.get("last_token_usage") or {}
                # last_token_usage.total_tokens ≈ context for that turn.
                peak_context_tokens = max(
                    peak_context_tokens,
                    int(last.get("total_tokens") or 0),
                    int((tot or {}).get("total_tokens") or 0),
                )
            elif etype == "user_message":
                user_turns += 1

        if rtype == "response_item":
            ptype = payload.get("type")
            if ptype in ("function_call", "custom_tool_call", "web_search_call"):
                tool_calls += 1
            if ptype == "message" and payload.get("role") in ("user", "assistant"):
                messages += 1
                if payload.get("role") == "user" and not first_user:
                    text = codex_message_text(record, "user", "input_text")
                    if text and usable_user_text(text):
                        first_user = text

        if not first_user:
            text = codex_message_text(record, "user", "input_text")
            if text and usable_user_text(text):
                first_user = text

    last_user = ""
    last_assistant = ""
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

    # Prefer event_msg user_message count; fall back to response_item users.
    if not user_turns and first_user:
        user_turns = 1 if last_user else 0
        # Recount usable user messages if event stream omitted them.
        if user_turns:
            n = 0
            for record in records:
                text = codex_message_text(record, "user", "input_text")
                if text and usable_user_text(text):
                    n += 1
            user_turns = n

    sort_ts = last_ts or meta.get("timestamp", "")
    session_id = meta.get("id", "") or meta.get("session_id", "")
    if not sort_ts or not session_id:
        return None

    usage = None
    if total_usage or tool_calls or user_turns or model:
        inp = int((total_usage or {}).get("input_tokens") or 0)
        out = int((total_usage or {}).get("output_tokens") or 0)
        # reasoning_output_tokens is billed/output-adjacent; fold into output.
        out += int((total_usage or {}).get("reasoning_output_tokens") or 0)
        cached = int((total_usage or {}).get("cached_input_tokens") or 0)
        if not peak_context_tokens:
            peak_context_tokens = int((total_usage or {}).get("total_tokens") or 0)
        usage = {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_tokens": cached,
            "cache_creation_tokens": 0,
            "tool_calls": tool_calls,
            "user_turns": user_turns,
            "messages": messages,
            "peak_context_tokens": peak_context_tokens,
            "duration_s": _duration_s(first_ts, last_ts or sort_ts),
            "model": model,
        }

    return {
        "source": "codex",
        "sort_ts": sort_ts,
        "cwd": meta.get("cwd", ""),
        "session_id": session_id,
        # Which client started the session: codex-tui / codex_vscode are
        # interactive; codex_exec / acpx / codex_cli_rs(mcp) are headless
        # automation. The UI badges non-interactive origins.
        "origin": meta.get("originator") or "",
        "title": "",
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": last_assistant,
        "usage": usage,
    }


def collect(limit):
    """Return up to `limit` Codex session entries (mtime-sorted candidates)."""
    return collect_jsonl(CODEX_GLOB, "codex", parse_codex, limit)


def delete_session(session_id):
    """Trash the rollout .jsonl whose session_meta carries this id."""
    def extract(record):
        if record.get("type") != "session_meta":
            return ""
        payload = record.get("payload") or {}
        return payload.get("id") or payload.get("session_id") or ""

    return delete_file_session(CODEX_GLOB, session_id, extract)
