"""Carbon intensity from a generation mix.

India's public grid data -- CEA's dashboards and Grid-India's (formerly POSOCO)
daily and real-time reports -- publishes generation by fuel, in MW, not carbon
intensity. Every carbon-intensity figure anywhere is that mix multiplied by
per-fuel emission factors, so doing the multiplication here is what turns a real
Indian generation report into something the scheduler can optimise on.

The factors below are direct combustion intensities in gCO2 per kWh generated,
the same basis the UK Carbon Intensity API publishes, so a GB figure and a
figure derived here mean the same thing and can sit on one axis. They are
standard published values, not measurements we made, and the result is labelled
"derived from an operator-supplied generation mix" rather than provider
telemetry.

Renewable share, unlike the national UK path, is genuinely computed here: the
mix says how much came from wind, solar, hydro and biomass, so it is measured
rather than back-calculated from intensity.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Tuple

# gCO2/kWh generated, direct combustion. Aliases cover the spellings CEA and
# Grid-India use across their exports.
EMISSION_FACTORS: Dict[str, float] = {
    "coal": 937.0,
    "lignite": 1050.0,
    "gas": 394.0,
    "ccgt": 394.0,
    "oil": 935.0,
    "diesel": 935.0,
    "naphtha": 700.0,
    "nuclear": 0.0,
    "hydro": 0.0,
    "wind": 0.0,
    "solar": 0.0,
    "biomass": 120.0,
    "bagasse": 120.0,
    "pumped_storage": 0.0,
    "battery": 0.0,
    "other": 300.0,
}

RENEWABLE_FUELS = frozenset({"hydro", "wind", "solar", "biomass", "bagasse"})

FACTOR_BASIS = (
    "direct combustion gCO2/kWh, the same basis the UK Carbon Intensity API "
    "publishes, so derived and provider figures are comparable"
)


def normalise_fuel(name: str) -> str:
    """Map a reported fuel label onto a known factor key."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "coal_thermal": "coal", "thermal": "coal", "thermal_coal": "coal",
        "gas_naphtha_diesel": "gas", "gas_turbine": "gas",
        "solar_pv": "solar", "wind_power": "wind",
        "large_hydro": "hydro", "small_hydro": "hydro", "hydel": "hydro",
        "res": "other", "other_res": "other", "renewable": "other",
        "nuclear_power": "nuclear", "storage": "battery",
    }
    key = aliases.get(key, key)
    return key if key in EMISSION_FACTORS else "other"


def intensity_from_mix(mix: Mapping[str, float]) -> Tuple[float, float, Dict[str, float]]:
    """(intensity gCO2/kWh, renewable %, normalised mix in MW).

    Raises ValueError when the mix carries no generation, because dividing by
    zero output would otherwise produce a confident-looking zero.
    """
    normalised: Dict[str, float] = {}
    for fuel, output in mix.items():
        value = float(output)
        if value < 0:
            raise ValueError(f"Generation for {fuel!r} cannot be negative")
        if value:
            normalised[normalise_fuel(fuel)] = normalised.get(normalise_fuel(fuel), 0.0) + value

    total = sum(normalised.values())
    if total <= 0:
        raise ValueError("Generation mix totals zero; nothing to derive an intensity from")

    emitted = sum(mw * EMISSION_FACTORS[f] for f, mw in normalised.items())
    renewable = sum(mw for f, mw in normalised.items() if f in RENEWABLE_FUELS)
    return round(emitted / total, 1), round(renewable / total * 100.0, 1), normalised


def unknown_fuels(mix: Iterable[str]) -> list[str]:
    """Labels that fell through to the generic 'other' factor, so callers can say so."""
    return sorted({
        name for name in mix
        if name.strip().lower().replace(" ", "_").replace("-", "_") not in EMISSION_FACTORS
        and normalise_fuel(name) == "other"
        and name.strip().lower() != "other"
    })
