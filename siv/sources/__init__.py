"""Per-tool session parsers.

Each module exposes collect(limit) -> list[dict], messages(session_id,
page, page_size) -> dict | None and delete_session(session_id).
"""

from . import claude, codex, copilot, devin, grok, opencode, pi

MODULES = {
    "claude": claude,
    "codex": codex,
    "copilot": copilot,
    "devin": devin,
    "grok": grok,
    "opencode": opencode,
    "pi": pi,
}
