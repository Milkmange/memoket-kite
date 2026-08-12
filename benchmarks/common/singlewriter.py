"""One writer per result tag, enforced across processes.

Every guard in this package assumes a single scorer owns the directory for the
duration of a run: the drift check compares what was observed against what is
there at seal time, and the seal digests the bytes this scorer wrote. Neither
survives two scorers on the same tag, and the overwrite guard cannot stand in
for exclusion — it is a no-op precisely when `judge_manifest.json` is absent,
which is the state two fresh concurrent scorers are both in.

The lock is advisory in the sense that it only stops processes that take it,
and deliberately refuses to break a lock it did not place: auto-stealing a
stale lock is the same race one level up.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import time
from pathlib import Path

LOCK_NAME = ".writer.lock"


def _alive(pid: int) -> bool:
    """Whether a local pid still exists.

    Signal 0 performs the permission and existence checks without delivering
    anything. `PermissionError` means the process is there but owned by another
    user, which is still a live holder.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def held(result_dir: Path, purpose: str = "scoring"):
    """Own `result_dir` for the duration of the block, or refuse to start.

    Claimed with `O_EXCL` so testing for the lock and taking it are one
    operation; a separate "does it exist" check would let two scorers both pass
    before either creates the file.

    A staleness verdict is only meaningful for a pid on this host, so the check
    is scoped to a matching hostname. It is reported to the operator rather
    than acted on: breaking a lock this process did not place reintroduces the
    race the lock exists to close.
    """
    path = result_dir / LOCK_NAME
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "purpose": purpose,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        try:
            holder = json.loads(path.read_text())
        except Exception:
            holder = {}
        pid, host = holder.get("pid"), holder.get("host")
        stale = host == socket.gethostname() and isinstance(pid, int) and not _alive(pid)
        detail = (
            f"pid {pid} on {host} since {holder.get('started', '?')}"
            if holder
            else "an unreadable lock file"
        )
        note = (
            f" That process is gone; if you are certain no scorer is running, "
            f"delete {path} and retry."
            if stale
            else " Wait for it to finish, or score under a different --tag."
        )
        raise SystemExit(
            f"{result_dir.name} is already being written by {detail} "
            f"({holder.get('purpose', '?')}).{note}"
        ) from None
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(payload)
        yield
    finally:
        # Only ever remove our own claim, so a crash-and-restart cannot delete
        # the lock a second scorer legitimately holds.
        with contextlib.suppress(Exception):
            if json.loads(path.read_text()).get("pid") == os.getpid():
                path.unlink()
