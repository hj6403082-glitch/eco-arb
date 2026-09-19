"""Atomic JSON writes that survive Windows file locking.

os.replace is atomic on POSIX and usually atomic on Windows, but Windows
raises PermissionError (WinError 5 / 32) whenever anything else holds a handle
on the target for an instant -- an antivirus scanner, the search indexer, or a
sync client such as OneDrive, which routinely watches C:\\Users\\<name>\\Documents.
The window is milliseconds, so a short retry clears it.

Persistence is a convenience here: it lets a restart keep the queue. It is never
worth failing a request over, so a checkpoint that cannot be written after all
retries logs and gives up rather than propagating.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("eco_arb.fsutil")

RETRIES = 6
BACKOFF_SECONDS = 0.05


def write_json_atomic(path: Path, payload: Any, *, label: str = "state") -> bool:
    """Write `payload` to `path` atomically. Returns False if it could not.

    Never raises on a locking failure: the caller is mid-request and losing a
    checkpoint is preferable to losing the request.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        log.warning("Could not stage %s to %s: %s", label, path, exc)
        return False

    for attempt in range(RETRIES):
        try:
            os.replace(temporary, path)
            return True
        except PermissionError:
            # Someone else holds the target for a moment. Back off and retry.
            if attempt == RETRIES - 1:
                break
            time.sleep(BACKOFF_SECONDS * (attempt + 1))
        except OSError as exc:
            log.warning("Could not save %s to %s: %s", label, path, exc)
            return False

    log.warning(
        "Could not save %s to %s after %d attempts: the file is locked by another "
        "process (antivirus, search indexer, or a sync client such as OneDrive). "
        "Continuing without persisting; the queue will not survive a restart.",
        label, path, RETRIES,
    )
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass
    return False
