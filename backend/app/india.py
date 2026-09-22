"""Indian grid data: a recorded real forecast, and the live providers.

The UK path needs none of this -- the Carbon Intensity API is open and
returns a generation mix. India has neither property, so this module carries
the three things the Indian grid needs that the British one does not.

1. Its own renewable calibration. carbon.derive_renewable_pct is fitted to
   the British grid and saturates at 400 gCO2/kWh, so every Indian value --
   which runs 450-700 -- collapsed to the 5% floor. The fit here comes from
   real paired observations instead.
2. A recorded provider forecast, so the Indian regions show genuine numbers
   with no API key and no network. It is replayed, and labelled as replayed.
3. Live provider clients, behind API keys, for when a key is present.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from pathlib import Path

import httpx

from .clock import iso, parse_iso
from .models import Grid

log = logging.getLogger(__name__)

RECORDED_PATH = Path(__file__).resolve().parent / "data" / "india_recorded.json"

# Least-squares fit over the five paired (intensity, renewable share)
# observations recorded on 2026-09-19, which span 457-550 gCO2/kWh and
# 28-41% renewable. R^2 = 0.97, every point within 1.6 percentage points.
# Five points is a small sample and the ends are extrapolation, so callers
# label this "derived", never "measured".
RENEWABLE_SLOPE = -0.13114
RENEWABLE_INTERCEPT = 100.852
RENEWABLE_BASIS = ("linear fit to 5 paired Electricity Maps / EnergyMap India "
                   "observations, 2026-09-19 (R^2 0.97); derived, not measured")

# Indian day-ahead and real-time prices are published in INR/kWh, while the
# rest of the system carries GBP/MWh. One conversion point, stated once.
INR_PER_GBP = 105.0


def derive_renewable_pct(intensity: float) -> float:
    """Renewable share for an Indian intensity, on the India fit."""
    return round(min(max(RENEWABLE_SLOPE * intensity + RENEWABLE_INTERCEPT, 0.0), 100.0), 1)


def inr_kwh_to_gbp_mwh(price_inr_kwh: float) -> float:
    """INR/kWh -> GBP/MWh, the unit the engine scores cost in."""
    return round(price_inr_kwh * 1000.0 / INR_PER_GBP, 2)


class RecordedIndia:
    """The recorded provider forecast, replayed against the displayed clock.

    The capture is a full 24 hours indexed by UTC half-hour-of-day, so a slot
    at 06:00 always carries what the provider actually forecast for 06:00.
    The shape is real; only the date it is shown against is not.
    """

    def __init__(self, path: Path = RECORDED_PATH) -> None:
        self.payload: dict | None = None
        self.error: str | None = None
        try:
            self.payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.error = f"{type(exc).__name__}: recorded India capture unavailable"
            log.warning("Could not load the recorded India capture at %s: %s", path, exc)

    @property
    def available(self) -> bool:
        return bool(self.payload and self.payload.get("intensity_by_half_hour_utc"))

    def source(self) -> str:
        if not self.available:
            return "No Indian data available"
        assert self.payload is not None
        return (f"{self.payload['provider']} forecast for zone "
                f"{self.payload['zone']}, recorded {self.payload['forecast_generated_at'][:10]} "
                "and replayed by half-hour of day")

    def observed(self) -> list[dict]:
        return list(self.payload.get("observed_conditions", [])) if self.payload else []

    def forecast(self, first_slot, count: int = 49) -> list[Grid]:
        """`count` half-hour rows starting at `first_slot`."""
        if not self.available:
            return []
        assert self.payload is not None
        table = self.payload["intensity_by_half_hour_utc"]
        rows = []
        for i in range(count):
            stamp = first_slot + timedelta(minutes=30 * i)
            key = "%02d:%02d" % (stamp.hour, 0 if stamp.minute < 30 else 30)
            value = table.get(key)
            if value is None:
                break
            rows.append(Grid(timestamp=iso(stamp), intensity_gco2_kwh=float(value),
                             renewable_pct=derive_renewable_pct(value),
                             price=_modelled_india_price(float(value)),
                             renewable_basis=RENEWABLE_BASIS,
                             live=False, source_kind="recorded_real"))
        return rows


def _modelled_india_price(intensity: float) -> float:
    """Placeholder price for a recorded slot.

    The capture holds real IEX prices for the hours it observed, but not for
    the forecast horizon, and inventing them would undo the point of using
    real data. This stays modelled and is reported as modelled; a live IEX
    key replaces it with the real thing.
    """
    frac = min(max((intensity - 450.0) / 250.0, 0.0), 1.0)
    return round(25.0 + 35.0 * frac, 2)


def fetch_live_mix(api_key: str, *, timeout: float = 12.0) -> dict:
    """National fuel mix from EnergyMap India. Raises on any failure."""
    res = httpx.get("https://api.energymap.in/api/intelligence/national-fuelmix-4min",
                    headers={"X-API-Key": api_key}, timeout=timeout)
    res.raise_for_status()
    return res.json()


def fetch_live_price_inr_kwh(api_key: str, *, timeout: float = 12.0) -> float:
    """Latest IEX real-time-market clearing price, in INR/kWh."""
    res = httpx.get("https://api.energymap.in/developer/v1/market/iex/latest",
                    params={"market_type": "RTM"}, headers={"X-API-Key": api_key},
                    timeout=timeout)
    res.raise_for_status()
    payload = res.json()
    for key in ("price_inr_kwh", "price", "mcp", "clearing_price"):
        if isinstance(payload.get(key), (int, float)):
            return float(payload[key])
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("price_inr_kwh", "price", "mcp", "clearing_price"):
            if isinstance(data.get(key), (int, float)):
                return float(data[key])
    raise ValueError("IEX response carried no recognisable clearing price")


recorded_india = RecordedIndia()
