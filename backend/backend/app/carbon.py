"""Grid feed: UK Carbon Intensity API -> Grid slots on the virtual clock.

WHAT IS REAL AND WHAT IS NOT
----------------------------
* intensity_gco2_kwh -- REAL. Pulled from /intensity/fw24h (48 half-hour
  forecast slots, no API key). This is the only quantity the decision engine
  optimises on.
* renewable_pct -- DERIVED. /intensity/fw24h carries forecast intensity and a
  coarse index, not a generation mix, so the share is back-calculated from
  intensity with the documented linear calibration below. Display only.
* price -- MODELLED. The API carries no price at all. We use a scarcity proxy
  (gas sets the margin when carbon is high) with a demand-shaped evening peak.
  Display only, and labelled as modelled in the UI.

PHASING
-------
The 48 fetched slots span exactly 24h, i.e. every half-hour-of-day. We index
them by half-hour-of-day into a `day_profile`, so the grid feed becomes a pure
function of virtual wall-clock time. That keeps the diurnal curve correctly
phased to the displayed clock and lets a 360x demo run indefinitely without
outrunning the fetched window.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from . import config
from .clock import iso, parse_iso, real_now
from .models import Grid

SLOTS_PER_DAY = 48


def half_hour_of_day(dt: datetime) -> int:
    dt = dt.astimezone(timezone.utc)
    return (dt.hour * 60 + dt.minute) // config.SLOT_MINUTES


def floor_to_slot(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    minute = (dt.minute // config.SLOT_MINUTES) * config.SLOT_MINUTES
    return dt.replace(minute=minute, second=0, microsecond=0)


def derive_renewable_pct(intensity: float) -> float:
    """Linear calibration: 0 gCO2/kWh -> 95% renewable, 400+ -> 5%."""
    span = config.RENEWABLE_AT_ZERO_INTENSITY - config.RENEWABLE_AT_MAX_INTENSITY
    frac = min(max(intensity / config.INTENSITY_CALIBRATION_MAX, 0.0), 1.0)
    return round(config.RENEWABLE_AT_ZERO_INTENSITY - span * frac, 1)


def model_price(intensity: float, slot_start: datetime) -> float:
    """Modelled day-ahead price, GBP/MWh.

    Two terms: a scarcity term linear in carbon intensity (dirty margin ==
    expensive margin), and a demand shape peaking at the 17:00-19:00 teatime
    ramp. Neither is measured; this is a plausible curve, not a forecast.
    """
    frac = min(max(intensity / config.INTENSITY_CALIBRATION_MAX, 0.0), 1.0)
    scarcity = config.PRICE_FLOOR_GBP_MWH + (
        config.PRICE_CEIL_GBP_MWH - config.PRICE_FLOOR_GBP_MWH
    ) * frac
    hour = slot_start.astimezone(timezone.utc).hour + slot_start.minute / 60.0
    demand = 1.0 + 0.18 * math.exp(-((hour - 18.0) ** 2) / 6.0)
    return round(scarcity * demand, 2)


def synthetic_day_profile() -> Dict[int, float]:
    """Offline fallback shaped like a UK winter weekday.

    Overnight wind trough, a midday solar dip, a hard evening gas peak. Used
    only when the live API is unreachable; every slot it produces is flagged
    live=False and the UI says so.
    """
    profile: Dict[int, float] = {}
    for hh in range(SLOTS_PER_DAY):
        hour = hh * config.SLOT_MINUTES / 60.0
        base = 210.0
        overnight = -70.0 * math.exp(-((hour - 3.0) ** 2) / 8.0)
        solar = -55.0 * math.exp(-((hour - 13.0) ** 2) / 6.0)
        evening = 95.0 * math.exp(-((hour - 18.5) ** 2) / 3.5)
        morning = 30.0 * math.exp(-((hour - 8.0) ** 2) / 2.5)
        profile[hh] = round(max(20.0, base + overnight + solar + evening + morning), 1)
    return profile


class GridFeed:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._profile: Dict[int, float] = synthetic_day_profile()
        self._live = False
        self._rows = {}
        self._last_fetch_iso: Optional[str] = None
        self._last_error: Optional[str] = None

    @property
    def live(self) -> bool:
        with self._lock:
            return self._live

    def status(self) -> dict:
        with self._lock:
            return {
                "live": self._live,
                "source": "UK Carbon Intensity API /intensity/fw24h"
                if self._live
                else ("cached UK forecast" if self._last_fetch_iso else "offline fallback curve"),
                "last_fetch_iso": self._last_fetch_iso,
                "last_error": self._last_error,
                "cached": bool(self._last_error and self._last_fetch_iso),
                "profile_extension": True,
            }

    def refresh(self) -> bool:
        """Pull /intensity/fw24h. Returns True if the live pull succeeded.

        A failure is not fatal: we keep serving the last good profile (or the
        synthetic one) so a flaky conference wifi cannot kill the demo.
        """
        url = f"{config.CARBON_API_BASE}{config.FORECAST_PATH}"
        try:
            resp = httpx.get(url, timeout=10.0, headers={"Accept": "application/json"})
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data") or []
            profile: Dict[int, float] = {}
            exact_rows = {}
            for row in rows:
                intensity = (row.get("intensity") or {}).get("forecast")
                if intensity is None:
                    continue
                start = parse_iso(row["from"])
                profile[half_hour_of_day(start)] = float(intensity)
                exact_rows[iso(start)] = float(intensity)
            if len(profile) < SLOTS_PER_DAY // 2:
                raise ValueError(
                    f"forecast covered only {len(profile)} of {SLOTS_PER_DAY} half-hours"
                )
            # Fill any half-hour the response did not cover by carrying the
            # nearest known neighbour, so the profile is always total.
            known = sorted(profile)
            for hh in range(SLOTS_PER_DAY):
                if hh not in profile:
                    nearest = min(known, key=lambda k: min(abs(k - hh), SLOTS_PER_DAY - abs(k - hh)))
                    profile[hh] = profile[nearest]
            with self._lock:
                self._profile = profile
                self._rows = exact_rows
                self._live = True
                self._last_fetch_iso = iso(real_now())
                self._last_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - any failure degrades the same way
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._live = False
            return False

    def intensity_at(self, when: datetime) -> float:
        with self._lock:
            return self._profile[half_hour_of_day(when)]

    def slot_at(self, when: datetime) -> Grid:
        start = floor_to_slot(when)
        return self._build(start)

    def forecast(self, start_from: datetime, hours: int = config.DEADLINE_HORIZON_HOURS) -> List[Grid]:
        """Grid slots covering [floor(start_from), +hours), on the virtual clock."""
        first = floor_to_slot(start_from)
        count = int(hours * 60 / config.SLOT_MINUTES) + 1
        return [
            self._build(first + timedelta(minutes=config.SLOT_MINUTES * k))
            for k in range(count)
        ]

    def _build(self, start: datetime) -> Grid:
        with self._lock:
            exact = iso(start) in self._rows
            intensity = self._rows[iso(start)] if exact else self._profile[half_hour_of_day(start)]
            live = self._live and exact
            source = "provider_forecast" if live else ("cached" if exact else ("profile_replay" if self._last_fetch_iso else "synthetic_fallback"))
        return Grid(
            timestamp=iso(start),
            intensity_gco2_kwh=round(intensity, 1),
            renewable_pct=derive_renewable_pct(intensity),
            price=model_price(intensity, start),
            live=live,
            source_kind=source,
        )


feed = GridFeed()
