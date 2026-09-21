"""Build resume shell commands and open them in a macOS terminal."""

import os
import shlex
import subprocess

from .config import TERMINAL_APP
from .host import resolve_resume_cwd


def resume_command(source, session_id, cwd):
    if source == "devin":
        base = f"devin -r {session_id}"
    elif source == "claude":
        base = f"claude --resume {session_id}"
    elif source == "grok":
        base = f"grok --resume {session_id}"
    elif source == "pi":
        base = f"pi --session {session_id}"
    elif source == "copilot":
        base = f"copilot --resume {session_id}"
    elif source == "opencode":
        base = f"opencode --session {session_id}"
    else:
        base = f"codex resume {session_id}"
    resolved_cwd = resolve_resume_cwd(cwd)
    return f"cd {shlex.quote(resolved_cwd)} && {base}" if resolved_cwd else base


def detect_terminal():
    if TERMINAL_APP != "auto":
        return TERMINAL_APP
    for app in ("Ghostty", "iTerm"):
        if os.path.isdir(f"/Applications/{app}.app"):
            return app
    return "Terminal"


def open_in_terminal(command):
    app = detect_terminal()
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    if app == "Ghostty":
        # Ghostty >= 1.3 ships an AppleScript dictionary
        # (ghostty-org/ghostty#11208). `new tab in front window` reuses the
        # running instance instead of spawning a second Dock icon the way
        # `open -na` does. The command goes through `initial input` so it
        # runs in the user's login shell and the tab stays open after the
        # command exits — same semantics as Terminal's `do script`. A
        # trailing `return` submits the line (initial input is pasted text,
        # not a keypress).
        script = (
            'tell application "Ghostty"\n'
            "  set cfg to new surface configuration\n"
            f'  set initial input of cfg to "{escaped}" & return\n'
            "  if (count of windows) > 0 then\n"
            "    new tab in front window with configuration cfg\n"
            "  else\n"
            "    new window with configuration cfg\n"
            "  end if\n"
            "  activate\n"
            "end tell"
        )
        if subprocess.run(["osascript", "-e", script]).returncode == 0:
            return
        # Fallback for Ghostty < 1.3 (no AppleScript dictionary): `open -na`
        # launches a throwaway instance — -e implies
        # quit-after-last-window-closed. -e expects argv with no shell
        # interpretation, so wrap in `zsh -l -c` to handle `&&`, PATH, and
        # aliases from the user's shell config. --window-save-state=never
        # prevents restoring the previous window layout.
        subprocess.Popen(
            [
                "open",
                "-na",
                "Ghostty.app",
                "--args",
                "--window-save-state=never",
                "-e",
                "zsh",
                "-l",
                "-c",
                command,
            ]
        )
        return

    if app == "iTerm":
        script = (
            'tell application "iTerm"\n'
            "  create window with default profile\n"
            "  tell current session of current window\n"
            f'    write text "{escaped}"\n'
            "  end tell\n"
            "end tell"
        )
    else:
        # Terminal.app — `do script` first creates the window with the
        # command; the leading `activate` from earlier versions spawned an
        # extra empty window before `do script` ran.
        script = (
            'tell application "Terminal"\n'
            f'  do script "{escaped}"\n'
            "  activate\n"
            "end tell"
        )
    subprocess.Popen(["osascript", "-e", script])
