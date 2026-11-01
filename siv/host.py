"""Host labels and cwd remapping for multi-machine sessions."""

import os

from .config import CURRENT_CWD, HOME_DIR_RE, IS_WINDOWS, LOCAL_HOME, LOCAL_USER


def _under_home(cwd):
    if IS_WINDOWS:
        # Case-insensitive, and either separator may appear.
        home = LOCAL_HOME.lower().replace("/", "\\").rstrip("\\")
        path = cwd.lower().replace("/", "\\")
        return path == home or path.startswith(home + "\\")
    return cwd == LOCAL_HOME or cwd.startswith(LOCAL_HOME + "/")


def host_for(cwd):
    if not cwd:
        return LOCAL_USER
    if _under_home(cwd):
        return LOCAL_USER
    match = HOME_DIR_RE.match(cwd)
    if match:
        return match.group(1) or match.group(2)
    return LOCAL_USER


def resolve_resume_cwd(cwd):
    """Map a recorded session cwd to something usable on this machine."""
    cwd = (cwd or "").strip()
    if cwd and os.path.isdir(cwd):
        return cwd

    match = HOME_DIR_RE.match(cwd)
    if match:
        if match.group(2):
            # Windows cwd: either separator, rebuilt with this OS's own.
            parts = [p for p in cwd[match.end() :].replace("\\", "/").split("/") if p]
            candidate = os.path.join(LOCAL_HOME, *parts) if parts else LOCAL_HOME
        else:
            suffix = cwd[match.end() :].lstrip("/")
            candidate = os.path.join(LOCAL_HOME, suffix) if suffix else LOCAL_HOME
        if os.path.isdir(candidate):
            return candidate

    return CURRENT_CWD
