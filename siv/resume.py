"""Build resume shell commands and open them in a terminal (macOS / Windows)."""

import os
import shlex
import shutil
import subprocess

from .config import IS_WINDOWS, TERMINAL_APP
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
    if not resolved_cwd:
        return base
    if IS_WINDOWS:
        # PowerShell syntax: Windows PowerShell 5.1 has no `&&`, and a
        # single-quoted literal only needs its own quotes doubled.
        quoted = "'" + resolved_cwd.replace("'", "''") + "'"
        return f"Set-Location -LiteralPath {quoted}; {base}"
    return f"cd {shlex.quote(resolved_cwd)} && {base}"


def detect_terminal():
    if TERMINAL_APP != "auto":
        return TERMINAL_APP
    for app in ("Ghostty", "iTerm"):
        if os.path.isdir(f"/Applications/{app}.app"):
            return app
    return "Terminal"


def _open_windows_console(command):
    # A new console window running PowerShell; on Windows 11 it opens in
    # whatever the default terminal host is (usually Windows Terminal).
    # Prefer pwsh 7: Windows PowerShell's default Restricted policy blocks
    # the npm .ps1 shims that most of these CLIs install.
    shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
    subprocess.Popen(
        [shell, "-NoLogo", "-NoExit", "-Command", command],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def open_in_terminal(command):
    if IS_WINDOWS:
        _open_windows_console(command)
        return
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
        # interpretation, so wrap in `zsh -l -i -c` to handle `&&` and PATH.
        # -i matters: only an interactive zsh reads .zshrc, where aliases and
        # wrapper functions around the CLIs live, so this path behaves like
        # the AppleScript one. --window-save-state=never prevents restoring
        # the previous window layout.
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
                "-i",
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
