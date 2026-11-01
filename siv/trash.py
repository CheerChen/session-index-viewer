"""Deletion helpers: everything goes to the Trash, never unlink.

File/dir sources are moved into Trash wholesale. SQLite sources can't be
moved, so their rows are dumped to a JSON file in Trash before the rows
are deleted — the dump is the recoverable artifact either way.

macOS: ~/.Trash. Windows: the Recycle Bin, through SHFileOperationW. If
~/.Trash doesn't exist on a POSIX host, deletion is unavailable entirely;
callers should gate on trash_available().
"""

import json
import os
import shutil
import sqlite3
import tempfile
import time

from .config import IS_WINDOWS

TRASH_DIR = os.path.expanduser("~/.Trash")

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    class _SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("i64Size", ctypes.c_int64),
            ("i64NumItems", ctypes.c_int64),
        ]

    _FO_DELETE = 0x3
    # Recycle, no dialogs. FOF_ALLOWUNDO alone silently destroys what can't
    # be recycled; FOF_WANTNUKEWARNING asks first instead, and
    # _recycle() refuses drives without a Recycle Bin before that.
    _RECYCLE_FLAGS = (
        0x0040  # FOF_ALLOWUNDO
        | 0x0010  # FOF_NOCONFIRMATION
        | 0x0004  # FOF_SILENT
        | 0x0400  # FOF_NOERRORUI
        | 0x4000  # FOF_WANTNUKEWARNING
    )


def trash_available():
    return IS_WINDOWS or os.path.isdir(TRASH_DIR)


def _recycle(path):
    """Send a file or directory to the Windows Recycle Bin."""
    path = os.path.abspath(path)
    shell32 = ctypes.windll.shell32
    info = _SHQUERYRBINFO(cbSize=ctypes.sizeof(_SHQUERYRBINFO))
    root = os.path.splitdrive(path)[0] + "\\"
    if shell32.SHQueryRecycleBinW(root, ctypes.byref(info)) != 0:
        raise OSError(f"no Recycle Bin on {root}")
    op = _SHFILEOPSTRUCTW(
        wFunc=_FO_DELETE,
        pFrom=path + "\0",  # the list is double-NUL terminated
        fFlags=_RECYCLE_FLAGS,
    )
    code = shell32.SHFileOperationW(ctypes.byref(op))
    if code or op.fAnyOperationsAborted:
        raise OSError(f"SHFileOperationW failed ({code:#x})")
    if os.path.exists(path):
        raise OSError("item is still in place after recycling")


def _dest(name):
    # Prefix with an epoch stamp so repeat deletions never collide and
    # Trash sorts roughly by deletion time.
    stamp = int(time.time())
    for n in range(100):
        suffix = f"-{n}" if n else ""
        dest = os.path.join(TRASH_DIR, f"{stamp}{suffix}-{name}")
        if not os.path.exists(dest):
            return dest
    raise OSError("no free trash destination name")


def move_to_trash(path):
    """Move a file or directory into the Trash.

    Returns the destination; None on Windows, where the Recycle Bin keeps
    the original path for Restore.
    """
    if IS_WINDOWS:
        _recycle(path)
        return None
    dest = _dest(os.path.basename(path.rstrip("/")))
    try:
        os.rename(path, dest)
    except OSError:
        shutil.move(path, dest)
    return dest


def dump_to_trash(name, payload):
    """Write a JSON recovery dump into the Trash.

    Returns the file path; None on Windows, where the dump is written to a
    temp folder and then recycled.
    """
    if IS_WINDOWS:
        folder = tempfile.mkdtemp(prefix="siv-")
        dest = os.path.join(folder, f"{int(time.time())}-{name}")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, default=str)
        _recycle(dest)
        os.rmdir(folder)
        return None
    dest = _dest(name)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)
    return dest


def _session_tables(conn):
    """All tables carrying a session_id column -> {name: [cols]}.

    Discovered dynamically because these app schemas drift between
    versions; a new child table is archived/deleted without a code change.
    """
    tables = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ):
        cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{name}")')]
        if "session_id" in cols:
            tables[name] = cols
    return tables


def dump_db_session(conn, main_table, session_id):
    """Read every row belonging to a session. Returns (dump, found).

    dump maps table -> list of row dicts: the main_table row keyed by
    `id`, plus every session_id-referencing row in other tables.
    """
    dump = {}
    for table, cols in _session_tables(conn).items():
        try:
            rows = conn.execute(
                f'SELECT * FROM "{table}" WHERE session_id = ?',
                (session_id,),
            ).fetchall()
            dump[table] = [dict(zip(cols, r)) for r in rows]
        except sqlite3.Error:
            continue
    main_cols = [
        c[1] for c in conn.execute(f'PRAGMA table_info("{main_table}")')
    ]
    rows = conn.execute(
        f'SELECT * FROM "{main_table}" WHERE id = ?', (session_id,)
    ).fetchall()
    dump[main_table] = [dict(zip(main_cols, r)) for r in rows]
    return dump, bool(rows)


def delete_db_session(db_path, main_table, session_id, source):
    """Dump then delete a session's rows from a SQLite session store.

    Archives all session_id-referencing rows plus the main session row to
    Trash first, then deletes them in one transaction.
    """
    if not os.path.isfile(db_path):
        return {"ok": False, "error": "Session store not found."}, 404
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return {"ok": False, "error": "Unable to open session store."}, 500
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        dump, found = dump_db_session(conn, main_table, session_id)
        if not found:
            return {"ok": False, "error": "Session not found."}, 404

        dump_to_trash(f"siv-{source}-{session_id}.json", dump)

        errors = []
        for table in _session_tables(conn):
            try:
                conn.execute(
                    f'DELETE FROM "{table}" WHERE session_id = ?',
                    (session_id,),
                )
            except sqlite3.Error as exc:
                errors.append(f"{table}: {exc}")
        conn.execute(
            f'DELETE FROM "{main_table}" WHERE id = ?', (session_id,)
        )
        conn.commit()
        result = {"ok": True}
        if errors:
            result["warnings"] = errors
        return result, 200
    except (sqlite3.Error, OSError):
        return {"ok": False, "error": "Could not delete this session."}, 500
    finally:
        conn.close()
