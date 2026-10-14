"""Claude Code sessions under ~/.claude/projects."""

from datetime import datetime

from ..config import CLAUDE_GLOB
from ..text import blocks_text, usable_user_text
from .jsonl_files import collect_jsonl, delete_file_session, file_messages

# Every record carries the client that wrote it: `cli` (TUI) and the IDE /
# desktop frontends are interactive; `sdk-cli` (`claude -p`), `sdk-ts` and
# `sdk-py` are programmatic runs with nobody at the keyboard.
HEADLESS_ENTRYPOINT_PREFIX = "sdk-"


def claude_user_text(record):
    content = (record.get("message") or {}).get("content")
    return content if isinstance(content, str) else ""


def _duration_s(first_ts, last_ts):
    if not first_ts or not last_ts:
        return 0
    try:
        a = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        b = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        return max(0, int((b - a).total_seconds()))
    except ValueError:
        return 0


def parse_claude(records):
    first_user = ""
    title = ""
    cwd = ""
    session_id = ""
    first_ts = ""
    last_ts = ""
    model = ""
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0
    tool_calls = 0
    user_turns = 0
    messages = 0
    peak_context_tokens = 0
    origin = ""
    # A headless run later resumed in the TUI counts as interactive, so
    # one non-SDK entrypoint anywhere clears the flag.
    interactive = False

    for record in records:
        entrypoint = record.get("entrypoint") or ""
        if entrypoint:
            origin = origin or entrypoint
            if not entrypoint.startswith(HEADLESS_ENTRYPOINT_PREFIX):
                interactive = True
        ts = record.get("timestamp") or ""
        if ts:
            if not first_ts:
                first_ts = ts
            last_ts = ts
        rtype = record.get("type")
        if rtype == "summary" and record.get("summary"):
            title = record["summary"]
        if not cwd and record.get("cwd"):
            cwd = record["cwd"]
        if not session_id and record.get("sessionId"):
            session_id = record["sessionId"]
        if rtype == "user":
            messages += 1
            text = claude_user_text(record)
            if usable_user_text(text):
                user_turns += 1
                if not first_user:
                    first_user = text
        elif rtype == "assistant":
            messages += 1
            msg = record.get("message") or {}
            if msg.get("model"):
                model = msg["model"]
            usage = msg.get("usage") or {}
            inp = int(usage.get("input_tokens") or 0)
            out = int(usage.get("output_tokens") or 0)
            cr = int(usage.get("cache_read_input_tokens") or 0)
            cc = int(usage.get("cache_creation_input_tokens") or 0)
            input_tokens += inp
            output_tokens += out
            cache_read_tokens += cr
            cache_creation_tokens += cc
            # Approximate context occupancy for this turn.
            peak_context_tokens = max(peak_context_tokens, inp + cr + cc)
            content = msg.get("content")
            if isinstance(content, list):
                tool_calls += sum(
                    1
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "tool_use"
                )

    last_user = ""
    last_assistant = None
    for record in reversed(records):
        rtype = record.get("type")
        if last_assistant is None and rtype == "assistant":
            text = blocks_text((record.get("message") or {}).get("content"))
            if text.strip():
                last_assistant = (record, text)
        if not last_user and rtype == "user":
            text = claude_user_text(record)
            if usable_user_text(text):
                last_user = text
        if last_assistant and last_user:
            break

    if last_assistant is None:
        return None
    record, assistant_text = last_assistant
    cwd = cwd or record.get("cwd", "")
    session_id = session_id or record.get("sessionId", "")
    sort_ts = last_ts or record.get("timestamp", "")
    if not sort_ts or not session_id:
        return None

    usage = None
    if (
        input_tokens
        or output_tokens
        or cache_read_tokens
        or cache_creation_tokens
        or tool_calls
        or user_turns
        or model
    ):
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "tool_calls": tool_calls,
            "user_turns": user_turns,
            "messages": messages,
            "peak_context_tokens": peak_context_tokens,
            "duration_s": _duration_s(first_ts, last_ts or sort_ts),
            "model": model,
        }

    return {
        "source": "claude",
        "sort_ts": sort_ts,
        "cwd": cwd,
        "session_id": session_id,
        "origin": origin,
        "headless": bool(origin) and not interactive,
        "title": title,
        "first_user": first_user,
        "last_user": last_user,
        "last_assistant": assistant_text,
        "usage": usage,
    }


def collect(limit):
    """Return up to `limit` Claude session entries (mtime-sorted candidates)."""
    return collect_jsonl(CLAUDE_GLOB, "claude", parse_claude, limit)


def _session_id(record):
    return record.get("sessionId") or ""


def _events(records):
    """Main-thread user prompts and assistant blocks as conversation events.

    User records whose content is a list of tool_result blocks are the
    harness feeding tool output back, not a person typing — skipped.
    """
    for record in records:
        if record.get("isSidechain") or record.get("isMeta"):
            continue
        rtype = record.get("type")
        msg = record.get("message") or {}
        content = msg.get("content")
        ts = record.get("timestamp") or ""
        if rtype == "user":
            text = content if isinstance(content, str) else blocks_text(content)
            if text:
                yield {"role": "user", "content": text, "created_at": ts}
        elif rtype == "assistant" and isinstance(content, list):
            thinking = "\n".join(
                b.get("thinking", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "thinking"
            ).strip()
            yield {
                "role": "assistant",
                "content": blocks_text(content),
                "thinking": thinking,
                "tool_calls": sum(
                    1
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                ),
                "created_at": ts,
            }


def messages(session_id, page=1, page_size=50):
    return file_messages(
        CLAUDE_GLOB, session_id, _session_id, _events, page, page_size
    )


def delete_session(session_id):
    """Trash the .jsonl whose records carry this sessionId."""
    return delete_file_session(CLAUDE_GLOB, session_id, _session_id)
