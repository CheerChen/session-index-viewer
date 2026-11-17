#!/usr/bin/env python3
"""Local session index server for Claude Code, Codex, Devin, Grok, Pi, Copilot CLI, and opencode.

Serves the viewer HTML at / and a live session index at /api/sessions.
Sessions are parsed on demand with an in-memory cache keyed by
(path, mtime, size), so repeat requests only re-parse changed files.

Stdlib only. Binds 127.0.0.1 — session transcripts must never be
exposed beyond this machine.

Implementation lives in the `siv` package; this file remains the launchd
/ CLI entry point (`python3 server.py`).
"""

from siv.http_app import main

if __name__ == "__main__":
    main()
