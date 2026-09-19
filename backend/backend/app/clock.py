"""Time-compression clock.

The demo needs to watch a 24-hour carbon forecast play out in a few minutes,
so the *clock* and the *grid feed* are compressed. Nothing else is. The
executor runs real workloads at real wall-clock speed -- see executor.py.

Invariant: virtual time is continuous across a speed change. Changing speed
re-anchors rather than rescaling from the epoch, so the displayed clock never
jumps when the operator flips 1x -> 360x.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from . import config


def real_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    cleaned = text.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class VirtualClock:
    def __init__(self, speed: int = 1) -> None:
        self._lock = threading.Lock()
        self._speed = speed
        self._anchor_real = real_now()
        self._anchor_virtual = self._anchor_real

    @property
    def speed(self) -> int:
        with self._lock:
            return self._speed

    def now(self) -> datetime:
        with self._lock:
            return self._now_locked()

    def _now_locked(self) -> datetime:
        elapsed_real = (real_now() - self._anchor_real).total_seconds()
        return self._anchor_virtual + timedelta(seconds=elapsed_real * self._speed)

    def set_speed(self, speed: int) -> int:
        if speed not in config.ALLOWED_SPEEDS:
            raise ValueError(
                f"speed must be one of {config.ALLOWED_SPEEDS}, got {speed}"
            )
        with self._lock:
            # Re-anchor at the current virtual instant so the clock is
            # continuous across the change.
            self._anchor_virtual = self._now_locked()
            self._anchor_real = real_now()
            self._speed = speed
            return self._speed

    def reset(self) -> None:
        with self._lock:
            self._anchor_real = real_now()
            self._anchor_virtual = self._anchor_real

    def real_seconds_until(self, target: datetime) -> float:
        """How many REAL seconds until the virtual clock reaches `target`."""
        with self._lock:
            delta = (target - self._now_locked()).total_seconds()
            return delta / self._speed


clock = VirtualClock()
