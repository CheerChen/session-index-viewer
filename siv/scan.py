"""Merge session entries from all sources into the API response shape."""

import glob
import os

from . import cache
from .config import CLAUDE_GLOB, CODEX_GLOB, PI_GLOB
from .host import host_for
from .resume import resume_command
from .sources import claude, codex, copilot, devin, grok, opencode, pi
from .sources.jsonl_files import cached_entry
from .trash import trash_available


def scan_sessions(limit):
    # Claude + Codex + Pi share one mtime-ranked candidate list so a flood
    # of files from one tool cannot starve the others within `limit`.
    candidates = []
    for path in glob.glob(CLAUDE_GLOB):
        candidates.append((path, claude.parse_claude))
    for path in glob.glob(CODEX_GLOB):
        candidates.append((path, codex.parse_codex))
    for path in glob.glob(PI_GLOB):
        candidates.append((path, pi.parse_pi))

    stats = []
    for path, parser in candidates:
        try:
            stats.append((os.stat(path).st_mtime, path, parser))
        except OSError:
            continue
    stats.sort(reverse=True)

    with cache.lock():
        items = []
        seen = set()
        for _, path, parser in stats[:limit]:
            entry = cached_entry(path, parser)
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
        for entry in devin.collect(limit):
            key = f"devin|{entry['session_id']}"
            if key in seen:
                continue
            seen.add(key)
            items.append(entry)

        # Grok CLI: per-session directories under ~/.grok/sessions.
        for entry in grok.collect(limit):
            key = f"grok|{entry['session_id']}"
            if key in seen:
                continue
            seen.add(key)
            items.append(entry)

        # Copilot CLI: relational SQLite store (~/.copilot/session-store.db).
        for entry in copilot.collect(limit):
            key = f"copilot|{entry['session_id']}"
            if key in seen:
                continue
            seen.add(key)
            items.append(entry)

        # opencode: single SQLite store with message/part tables.
        for entry in opencode.collect(limit):
            key = f"opencode|{entry['session_id']}"
            if key in seen:
                continue
            seen.add(key)
            items.append(entry)

    items.sort(key=lambda e: e["sort_ts"], reverse=True)
    items = items[:limit]
    deletable = trash_available()
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
            "usage": e.get("usage"),
            "deletable": deletable,
            "origin": e.get("origin") or "",
        }
        for e in items
    ]
