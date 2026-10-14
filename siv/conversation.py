"""Shared conversation projection for the /api/session detail view.

Each source turns its raw records into a flat list of events:
  {"role": "user" | "assistant", "content": str,
   "created_at"?: str, "thinking"?: str, "tool_calls"?: int}
fold_turns() collapses the assistant events of one user turn into a single
reply (the last non-empty text wins, tool calls are summed) and paginate()
slices the result into the shape the frontend expects.
"""

import math
import threading
from collections import OrderedDict

from .text import usable_user_text

# Parsed conversations of recently opened file-backed sessions, keyed by
# (path, mtime_ns, size). Small on purpose: only the detail pane reads it.
_LRU_SIZE = 32
_lru = OrderedDict()
_lru_lock = threading.Lock()


def cached(key, build):
    with _lru_lock:
        if key in _lru:
            _lru.move_to_end(key)
            return _lru[key]
    value = build()
    with _lru_lock:
        _lru[key] = value
        _lru.move_to_end(key)
        while len(_lru) > _LRU_SIZE:
            _lru.popitem(last=False)
    return value


def _has_reply(message):
    content = message.get("content")
    return isinstance(content, str) and bool(content.strip())


def fold_turns(events):
    """Return user turns and one combined assistant reply per turn.

    User events that are injected boilerplate (see usable_user_text) are
    dropped. An assistant side with neither text nor tool calls is dropped
    too; one that only ran tools (e.g. an aborted turn) is kept so the
    tool count stays visible.
    """
    messages = []
    assistant = None

    def flush():
        if assistant and (_has_reply(assistant) or assistant["tool_call_count"]):
            messages.append(assistant)

    for event in events:
        role = event.get("role")
        content = event.get("content") or ""
        if role == "user":
            if not usable_user_text(content):
                continue
            flush()
            assistant = None
            messages.append(
                {
                    "node_id": event.get("node_id", len(messages)),
                    "role": "user",
                    "content": content.strip(),
                    **(
                        {"created_at": event["created_at"]}
                        if event.get("created_at")
                        else {}
                    ),
                }
            )
            continue
        if role != "assistant":
            continue
        if assistant is None:
            assistant = {
                "node_id": event.get("node_id", len(messages)),
                "role": "assistant",
                "content": "",
                "tool_call_count": 0,
            }
        if event.get("node_id") is not None:
            assistant["node_id"] = event["node_id"]
        for key in ("created_at", "content", "thinking"):
            if event.get(key):
                assistant[key] = event[key]
        assistant["tool_call_count"] += int(event.get("tool_calls") or 0)
    flush()
    return messages


def paginate(all_messages, page, page_size):
    """Slice one page. page <= 0 means the last page (newest messages)."""
    total = len(all_messages)
    pages = math.ceil(total / page_size) if total else 1
    if page <= 0:
        page = pages
    page = min(page, pages)
    offset = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "messages": all_messages[offset : offset + page_size],
    }
