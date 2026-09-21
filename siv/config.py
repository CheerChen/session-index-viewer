"""Paths, limits, and shared regexes."""

import os
import re

PORT = 7333
BIND = "127.0.0.1"

# Repo root (parent of the siv package).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAVICON_PATH = os.path.join(ROOT, "favicon.svg")

# Production: serve the built React bundle from frontend/dist/. Dev
# mode uses Vite's dev server (:5173) with a proxy to :7333, so this
# path only matters when running server.py standalone.
DIST_PATH = os.path.join(ROOT, "frontend", "dist")
INDEX_HTML = os.path.join(DIST_PATH, "index.html")
# Fall back to the legacy single-file viewer if the bundle hasn't
# been built yet.
LEGACY_HTML = os.path.join(ROOT, "sessions-index.html")

CLAUDE_GLOB = os.path.expanduser("~/.claude/projects/*/*.jsonl")
CODEX_GLOB = os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl")

# Pi agent sessions: ~/.pi/agent/sessions/<encoded-cwd>/<ts>_<uuid>.jsonl.
# Per-file JSONL (session/model_change/message records), so it merges into
# the same mtime-ranked candidate list as Claude/Codex.
PI_GLOB = os.path.expanduser("~/.pi/agent/sessions/*/*.jsonl")

DEVIN_DB = os.path.expanduser("~/.local/share/devin/cli/sessions.db")

# GitHub Copilot CLI: one SQLite store with a clean turns table
# (pre-formatted user/assistant text) and per-turn usage events.
COPILOT_DB = os.path.expanduser("~/.copilot/session-store.db")

# opencode: single SQLite store. Conversation text lives in `part` rows
# (type=text) linked to `message` rows (role). Session-level token sums
# and model are denormalised onto the `session` row.
OPENCODE_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")

# Grok sessions live under $GROK_HOME/sessions/<encoded-cwd>/<uuid>/
# (default GROK_HOME is ~/.grok). Each session is a directory of JSON/JSONL
# files; summary.json is the index entry and updates.jsonl is the
# authoritative conversation stream used by `grok --resume`.

# Sessions synced across machines (e.g. via syncthing) keep the cwd
# they were recorded with. host_for() infers a label from the home-dir
# prefix: cwds under /Users/<name>/ or /home/<name>/ are labelled with
# that <name>, including this machine's own home.
LOCAL_HOME = os.path.expanduser("~")
HOME_DIR_RE = re.compile(r"^/(?:Users|home)/([^/]+)")
LOCAL_USER = os.path.basename(LOCAL_HOME.rstrip("/")) or "unknown"
CURRENT_CWD = os.getcwd() if os.path.isdir(os.getcwd()) else LOCAL_HOME

DEFAULT_LIMIT = 1000
MAX_LIMIT = 1000
CLIP_LEN = 360

# Files larger than this are read head + tail only; smaller ones whole.
FULL_READ_LIMIT = 2 * 1024 * 1024
HEAD_BYTES = 512 * 1024
TAIL_BYTES = 1024 * 1024

# User texts that are harness/CLI noise, not something the human typed.
SKIP_USER_PREFIXES = (
    "Caveat:",
    "<command-",
    "<local-command",
    "<system-reminder",
    "<user-prompt-submit-hook",
    "<environment_context>",
    "<turn_aborted>",
    "<skill-context",
    # Codex injects its installable-plugin marketplace list as a user-role
    # message at session bootstrap (plugins.recommendations).
    "<recommended_plugins",
)

SESSION_ID_RE = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{6,62}[0-9a-fA-F]$")

# Devin CLI session IDs are memorable word-pair slugs (e.g. "foamy-package").
DEVIN_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,62}$")

# opencode session IDs are "ses_" + base62-ish payload (e.g. "ses_00cb…").
OPENCODE_ID_RE = re.compile(r"^ses_[0-9A-Za-z]{8,64}$")

# Terminal app to use. "auto" prefers Ghostty > iTerm > Terminal based on
# what's installed. Override by setting to "Ghostty", "iTerm", or "Terminal".
TERMINAL_APP = "auto"

# Sources accepted by POST /api/resume.
RESUME_SOURCES = frozenset(
    {"claude", "codex", "devin", "grok", "pi", "copilot", "opencode"}
)
