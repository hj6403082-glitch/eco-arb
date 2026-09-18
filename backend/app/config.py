"""Central configuration for ECO-ARB."""
import os

# UK Carbon Intensity API (no key required).
CARBON_API_BASE = os.getenv("CARBON_API_BASE", "https://api.carbonintensity.org.uk")
FORECAST_PATH = "/intensity/fw24h"

# How often (in REAL seconds) we re-pull the forecast from the upstream API.
GRID_REFRESH_SECONDS = int(os.getenv("GRID_REFRESH_SECONDS", "300"))

# How often (in REAL seconds) the scheduler ticks to check for due jobs.
TICK_SECONDS = float(os.getenv("TICK_SECONDS", "1.0"))

# Deadline horizon for scheduling decisions.
DEADLINE_HORIZON_HOURS = 24

# Forecast slot width, fixed by the upstream API.
SLOT_MINUTES = 30

# Allowed time-compression factors for the demo clock.
ALLOWED_SPEEDS = (1, 60, 360)

# Below this carbon saving we do not bother deferring: run now.
MIN_SAVING_PCT = float(os.getenv("MIN_SAVING_PCT", "1.0"))

# Cost model (see carbon.py). Modelled, not measured -- display only.
PRICE_FLOOR_GBP_MWH = 35.0
PRICE_CEIL_GBP_MWH = 190.0

# Renewable-share calibration (see carbon.py). Derived, not measured.
RENEWABLE_AT_ZERO_INTENSITY = 95.0
RENEWABLE_AT_MAX_INTENSITY = 5.0
INTENSITY_CALIBRATION_MAX = 400.0

LOG_RING_SIZE = 200
