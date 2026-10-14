"""Pi agent sessions under ~/.pi/agent/sessions.

Per-session JSONL files whose records are a small tagged union:
  {type:"session", id, timestamp, cwd}          — one per file, the meta row
  {type:"model_change", modelId, provider}      — model switches
  {type:"message", message:{role, content, ...}} — the conversation

message.role is one of user / assistant / toolResult. content is a list of
blocks (type text / thinking / toolCall). Assistant messages carry a
per-turn `usage` object (input / output / cacheRead / cacheWrite /
reasoning / totalTokens) and `model`, which we aggregate into the shared
usage shape. Parsed via the same glob candidate list as Claude/Codex.
"""

from datetime import datetime

from ..config import PI_GLOB
from ..text import usable_user_text
from .jsonl_files import collect_jsonl, delete_file_session, file_messages


def _text_blocks(content):
    """Join visible text blocks; ignore thinking / toolCall blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
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


def parse_pi(records):
    meta = next((r for r in records if r.get("type") == "session"), None)
    if not meta:
        return None

    first_user = ""
    last_user = ""
    last_assistant = ""
    first_ts = meta.get("timestamp") or ""
    last_ts = ""
    model = ""

    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_write = 0
    tool_calls = 0
    user_turns = 0
    messages = 0
    peak_context = 0

    for record in records:
        ts = record.get("timestamp") or ""
        if ts:
            last_ts = ts
        if record.get("type") != "message":
            continue
        message = record.get("message") or {}
        role = message.get("role")
        content = message.get("content")

        if role == "user":
            text = _text_blocks(content)
            if text and usable_user_text(text):
                if not first_user:
                    first_user = text
                last_user = text
                user_turns += 1
                messages += 1
        elif role == "assistant":
            messages += 1
            text = _text_blocks(content)
            if text and text.strip():
                last_assistant = text
            if isinstance(content, list):
                tool_calls += sum(
                    1
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "toolCall"
                )
            usage = message.get("usage") or {}
            if usage:
                input_tokens += int(usage.get("input") or 0)
                output_tokens += int(usage.get("output") or 0)
                output_tokens += int(usage.get("reasoning") or 0)
                cache_read += int(usage.get("cacheRead") or 0)
                cache_write += int(usage.get("cacheWrite") or 0)
                peak_context = max(peak_context, int(usage.get("totalTokens") or 0))
            if message.get("model"):
                model = message["model"]

    if not last_assistant:
        return None

    sort_ts = last_ts or first_ts
    session_id = meta.get("id") or ""
    if not sort_ts or not session_id:
        return None

    usage = None
    if input_tokens or output_tokens or tool_calls or user_turns or model:
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_creation_tokens": cache_write,
            "tool_calls": tool_calls,
            "user_turns": user_turns,
            "messages": messages,
            "peak_context_tokens": peak_context,
            "duration_s": _duration_s(first_ts, sort_ts),
            "model": model,
        }

    return {
        "source": "pi",
        "sort_ts": sort_ts,
        "cwd": meta.get("cwd", ""),
        "session_id": session_id,
        "title": "",
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": last_assistant,
        "usage": usage,
    }


def collect(limit):
    """Return up to `limit` Pi session entries (mtime-sorted candidates)."""
    return collect_jsonl(PI_GLOB, "pi", parse_pi, limit)


def _session_id(record):
    if record.get("type") != "session":
        return ""
    return record.get("id") or ""


def _events(records):
    """user / assistant message records; toolResult rows are skipped."""
    for record in records:
        if record.get("type") != "message":
            continue
        msg = record.get("message") or {}
        role = msg.get("role")
        content = msg.get("content")
        ts = record.get("timestamp") or ""
        if role == "user":
            yield {"role": "user", "content": _text_blocks(content), "created_at": ts}
        elif role == "assistant":
            blocks = content if isinstance(content, list) else []
            yield {
                "role": "assistant",
                "content": _text_blocks(content),
                "thinking": "\n".join(
                    b.get("thinking", "")
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "thinking"
                ).strip(),
                "tool_calls": sum(
                    1
                    for b in blocks
                    if isinstance(b, dict) and b.get("type") == "toolCall"
                ),
                "created_at": ts,
            }


def messages(session_id, page=1, page_size=50):
    return file_messages(PI_GLOB, session_id, _session_id, _events, page, page_size)


def delete_session(session_id):
    """Trash the .jsonl whose session meta record carries this id."""
    return delete_file_session(PI_GLOB, session_id, _session_id)
