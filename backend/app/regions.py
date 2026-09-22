"""Region-aware data and planning. Spatial SHIFT is a local execution demo.

Live UK regions use the public NESO API. India accepts uploaded forecasts or
an optional Electricity Maps token. No synthetic Indian signal is labelled live.
"""
import math
import json
import os
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx

from .carbon import feed, floor_to_slot, derive_renewable_pct, model_price
from .india import recorded_india
from .india import derive_renewable_pct as derive_india_renewable_pct
from .fsutil import quarantine, write_json_atomic
from .clock import iso, parse_iso, real_now
from .engine import decide, score_window
from .learning import learned
from . import india
from .models import Grid

REGIONS = {
    "gb": {"name": "Great Britain", "country": "GB", "provider_id": None},
    "gb-london": {"name": "London", "country": "GB", "provider_id": 13},
    "gb-scotland": {"name": "North Scotland", "country": "GB", "provider_id": 1},
    "in": {"name": "India · National grid", "country": "IN", "zone": "IN"},
    "in-north": {"name": "India · Northern grid", "country": "IN", "zone": "IN-NO"},
    "in-south": {"name": "India · Southern grid", "country": "IN", "zone": "IN-SO"},
}


class RegionRegistry:
    def __init__(self, path=None):
        self.lock = threading.RLock()
        self.rows = {}
        self.sources = {}
        self.errors = {}
        self.mode = os.getenv("ECO_ARB_DEMO_MODE", "operational")
        self.scenario_anchor = floor_to_slot(real_now()) if self.mode == "scenario" else None
        self.path = path
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.rows = {k: [Grid(**r) for r in v] for k, v in data["rows"].items()}
                self.sources = data["sources"]
                self.errors = {k: "Restored forecast cache; awaiting refresh" for k, v in self.rows.items()
                               if any(r.source_kind != "imported" for r in v)}
            except (ValueError, TypeError, OSError, KeyError) as exc:
                self.rows, self.sources, self.errors = {}, {}, {}
                quarantine(path, str(exc), label="region forecast cache")

    def refresh(self):
        def fetch_region(key):
            region = REGIONS[key]
            try:
                if region["country"] == "GB":
                    stamp = iso(real_now())
                    url = f"https://api.carbonintensity.org.uk/regional/intensity/{stamp}/fw24h/regionid/{region['provider_id']}"
                    res = httpx.get(url, timeout=12)
                    res.raise_for_status()
                    payload = res.json()["data"]
                    if isinstance(payload, list):
                        payload = payload[0]
                    rows = []
                    for r in payload["data"]:
                        value = float(r["intensity"]["forecast"])
                        renew = sum(x["perc"] for x in r.get("generationmix", [])
                                    if x["fuel"] in ("wind", "solar", "hydro", "biomass"))
                        rows.append(Grid(timestamp=r["from"], intensity_gco2_kwh=value,
                                         renewable_pct=renew, price=model_price(value, parse_iso(r["from"])),
                                         renewable_basis="provider generation-mix forecast"))
                    source = "NESO regional forecast"
                else:
                    token = os.getenv("ELECTRICITY_MAPS_TOKEN")
                    if not token:
                        return
                    res = httpx.get("https://api.electricitymaps.com/v4/carbon-intensity/forecast",
                                    params={"zone": region["zone"], "horizonHours": 24, "emissionFactorType": "direct"},
                                    headers={"auth-token": token}, timeout=12)
                    res.raise_for_status()
                    rows = []
                    for r in res.json().get("forecast", []):
                        value = float(r["carbonIntensity"])
                        for offset in (0, 30):
                            stamp = parse_iso(r["datetime"]) + timedelta(minutes=offset)
                            rows.append(Grid(timestamp=iso(stamp), intensity_gco2_kwh=value,
                                             renewable_pct=derive_india_renewable_pct(value),
                                             price=model_price(value, stamp),
                                             renewable_basis=india.RENEWABLE_BASIS,
                                             source_kind="provider_forecast"))
                    source = "Electricity Maps direct-emissions forecast; hourly values held for two half-hours"
                if len(rows) < 2:
                    raise ValueError("Provider returned insufficient coverage")
                self.ingest(key, rows, source, imported=False)
            except Exception as exc:
                with self.lock:
                    self.errors[key] = type(exc).__name__ + ": provider unavailable"
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch_region, [k for k in REGIONS if k != "gb"]))

    def ingest(self, region, rows, source, imported=True, source_kind=None):
        if region not in REGIONS or len(rows) < 2:
            raise ValueError("A supported region and at least two rows are required")
        normalized = sorted(rows, key=lambda r: parse_iso(r.timestamp))
        for i, r in enumerate(normalized):
            stamp = parse_iso(r.timestamp)
            if stamp != floor_to_slot(stamp) or not math.isfinite(r.intensity_gco2_kwh) or not 0 <= r.intensity_gco2_kwh <= 1500:
                raise ValueError("Use finite 0–1500 gCO2/kWh values at UTC half-hour boundaries")
            if i and stamp - parse_iso(normalized[i-1].timestamp) != timedelta(minutes=30):
                raise ValueError("Forecast must have consecutive half-hour rows, without duplicates or gaps")
        with self.lock:
            kind = source_kind or ("imported" if imported else "provider_forecast")
            self.rows[region] = [r.model_copy(update={"live": not imported, "source_kind": kind})
                                 for r in normalized]
            self.sources[region] = source
            self.errors.pop(region, None)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(self.path,
                                  {"rows": {k: [r.model_dump() for r in v] for k, v in self.rows.items()},
                                   "sources": self.sources},
                                  label="imported region forecasts")

    def scenario(self, key, now):
        first = floor_to_slot(now)
        anchor = self.scenario_anchor or first
        rows = []
        for i in range(49):
            stamp = first + timedelta(minutes=30*i)
            elapsed = (stamp - anchor).total_seconds() / 3600
            # Deliberately distinct fixture windows for RUN, WAIT and SHIFT.
            base = {"gb": 310, "gb-london": 340, "gb-scotland": 45,
                    "in": 570, "in-north": 780, "in-south": 140}[key]
            trough = 0.24 if 2 <= elapsed % 24 < 5 else 1.0
            value = base * (trough if key in ("gb", "gb-london", "in-north") else 1)
            renewable = (derive_india_renewable_pct(value) if REGIONS[key]["country"] == "IN"
                         else derive_renewable_pct(value))
            rows.append(Grid(timestamp=iso(stamp), intensity_gco2_kwh=value,
                             renewable_pct=renewable, price=model_price(value, stamp),
                             live=False, source_kind="synthetic_scenario"))
        return rows

    def forecast(self, key, now, mode=None, method="provider"):
        if key not in REGIONS:
            raise ValueError("Unknown region")
        mode = mode or self.mode
        if method == "learned":
            if key != "gb":
                raise ValueError("The learned model is trained for GB national only")
            first = floor_to_slot(now)
            rows = []
            report = learned.status()
            if not report.get("trained"):
                raise ValueError("Train a model on the Intelligence page first")
            if mode != "scenario" and report.get("dataset") == "synthetic demonstration":
                raise ValueError("Synthetic-trained forecasts are restricted to scenario mode")
            for i in range(49):
                stamp = first + timedelta(minutes=30*i)
                value = learned.intensity(stamp)
                rows.append(Grid(timestamp=iso(stamp), intensity_gco2_kwh=value,
                                 renewable_pct=derive_renewable_pct(value), price=model_price(value, stamp),
                                 live=False, source_kind="learned_prediction"))
            return rows
        if mode == "scenario":
            return self.scenario(key, now)
        if key == "gb":
            return feed.forecast(now)
        with self.lock:
            rows = self.rows.get(key, [])
            stale = key in self.errors
            live = [r.model_copy(update={"live": False, "source_kind": "cached"}) if stale else r.model_copy()
                    for r in rows if parse_iso(r.timestamp) + timedelta(minutes=30) > now]
        if live:
            return live
        # Nothing imported and no provider connected. The national Indian grid
        # has a recorded real forecast to fall back on; it is real data on a
        # replayed clock, and labelled "recorded_real" so it is never mistaken
        # for a live pull.
        if key == "in" and recorded_india.available:
            return recorded_india.forecast(floor_to_slot(now))
        return live

    def describe(self, now):
        result = []
        for key, region in REGIONS.items():
            rows = self.forecast(key, now)
            result.append({"id": key, "name": region["name"], "country": region["country"],
                           "available": bool(rows), "current": rows[0].model_dump() if rows else None,
                           "source": "synthetic demonstration" if self.mode == "scenario" else
                                     (feed.status()["source"] if key == "gb" else
                                      self.sources.get(key) or
                                      (recorded_india.source() if key == "in" and recorded_india.available else
                                       "No provider connected; import a forecast or use scenario mode")),
                           "error": self.errors.get(key), "execution": "local demonstration only"})
        return result

    def plan(self, job, now):
        home = self.forecast(job.home_region, now, job.data_mode, job.forecast_method)
        baseline = score_window(home, now, job.duration_minutes, job.energy_kwh)
        if baseline is None:
            raise ValueError("Selected region does not have contiguous forecast coverage for this workload")
        best = decide(job, home, now)
        best.source_region = job.home_region
        best.target_region = job.home_region
        best.data_basis = ", ".join(sorted({r.source_kind for r in home}))
        alternatives = []
        if job.allow_shift:
            for key in job.allowed_regions:
                if key == job.home_region:
                    continue
                rows = self.forecast(key, now, job.data_mode)
                if score_window(rows, now, job.duration_minutes, job.energy_kwh) is None:
                    continue
                d = decide(job, rows, now)
                alternatives.append({"region": key, "run_at_iso": d.run_at_iso,
                                     "estimated_carbon_g": d.optimal_carbon_g,
                                     "data_basis": ", ".join(sorted({r.source_kind for r in rows}))})
                if d.optimal_carbon_g < best.optimal_carbon_g - 1e-6:
                    best = d
                    best.source_region, best.target_region = job.home_region, key
                    best.data_basis = alternatives[-1]["data_basis"]
        best.alternatives = alternatives
        best.baseline_carbon_g, best.baseline_cost_gbp = round(baseline[0], 3), round(baseline[1], 5)
        best.carbon_saved_pct = round((baseline[0]-best.optimal_carbon_g)/baseline[0]*100, 2) if baseline[0] else 0
        best.cost_saved_pct = round((baseline[1]-best.optimal_cost_gbp)/baseline[1]*100, 2) if baseline[1] else 0
        if best.target_region != job.home_region:
            best.action = "SHIFT"
            best.reason = (f"Recommend {REGIONS[best.target_region]['name']} at {best.run_at_iso}: "
                           f"{best.carbon_saved_pct:.1f}% lower scenario emissions than immediate execution in "
                           f"{REGIONS[job.home_region]['name']}. CPU work executes locally, not in that region. "
                           "Transfer emissions assumed zero for the built-in self-contained workload; "
                           "not applicable to data migration.")
        return best


registry = RegionRegistry(Path(os.getenv("ECO_ARB_STATE", Path(__file__).resolve().parents[1] / "data" / "state.json")).with_name("regions.json"))
