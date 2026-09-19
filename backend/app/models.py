"""Wire contract for ECO-ARB.

The three contract objects are Job, Grid and Decision. Fields marked
"extension" are additions the contract does not name but the executor and
the decision engine genuinely need; every contract field is present and
spelled exactly as specified.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

JobStatus = Literal["QUEUED", "WAITING", "RUNNING", "DONE", "FAILED", "MISSED"]
Action = Literal["RUN", "WAIT", "SHIFT"]


class Job(BaseModel):
    id: str
    name: str
    energy_kwh: float
    deadline_iso: str
    status: JobStatus = "QUEUED"

    # --- extensions ---
    # A window has to have a width before you can slide it, so the engine
    # needs a duration. Real wall-clock minutes; never time-compressed.
    duration_minutes: float = 30.0
    # Which real workload to execute. See executor.WORKLOADS.
    workload: str = "hash_grind"
    # True when the operator picked this window from the ranked recommendations
    # rather than letting the engine choose; the scheduler then leaves it alone.
    pinned: bool = False
    submitted_iso: Optional[str] = None
    run_at_iso: Optional[str] = None
    started_iso: Optional[str] = None
    finished_iso: Optional[str] = None
    result: Optional[dict] = None
    progress: float = 0.0
    home_region: str = "gb"
    allowed_regions: list[str] = Field(default_factory=list)
    allow_shift: bool = False
    target_region: str = "gb"
    forecast_method: Literal["provider", "learned"] = "provider"
    execution_mode: str = "local_demo"
    data_mode: str = "operational"
    execution_plan: Optional[dict] = None
    baseline_plan: Optional[dict] = None


class Grid(BaseModel):
    timestamp: str
    intensity_gco2_kwh: float = Field(ge=0, le=1500, allow_inf_nan=False)
    renewable_pct: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    price: float = Field(default=0, ge=0, allow_inf_nan=False)

    # --- extensions ---
    # True when intensity came from the live UK Carbon Intensity API,
    # False when it came from the offline fallback curve.
    live: bool = True
    source_kind: str = "provider_forecast"
    renewable_basis: str = "derived proxy"


class Decision(BaseModel):
    job_id: str
    action: Action
    run_at_iso: str
    carbon_saved_pct: float
    cost_saved_pct: float
    reason: str

    # --- extensions: what the terminal needs to draw the decision ---
    baseline_carbon_g: float = 0.0
    optimal_carbon_g: float = 0.0
    baseline_cost_gbp: float = 0.0
    optimal_cost_gbp: float = 0.0
    window_end_iso: str = ""
    decided_at_iso: str = ""
    slots_considered: int = 0
    feasible_windows: int = 0
    source_region: str = "gb"
    target_region: str = "gb"
    execution_mode: str = "local_demo"
    data_basis: str = "forecast estimate"
    alternatives: list[dict] = Field(default_factory=list)
    transfer_carbon_g: float = 0.0


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    energy_kwh: float = Field(gt=0, le=10000, allow_inf_nan=False)
    deadline_iso: Optional[str] = None
    deadline_hours: Optional[float] = Field(default=None, gt=0, le=24, allow_inf_nan=False)
    duration_minutes: float = Field(default=30.0, gt=0, le=1440, allow_inf_nan=False)
    workload: str = "hash_grind"
    home_region: str = "gb"
    allowed_regions: list[str] = Field(default_factory=list, max_length=8)
    allow_shift: bool = False
    forecast_method: Literal["provider", "learned"] = "provider"
    # Optional: a window chosen from /api/recommend. Omit to let the engine pick.
    run_at_iso: Optional[str] = None


class ModelTraining(BaseModel):
    dataset: Literal["public_history", "synthetic_demo"] = "public_history"


class ForecastImport(BaseModel):
    region: Literal["in-north", "in-south"]
    source_name: str = Field(min_length=3, max_length=120)
    rows: list[Grid] = Field(min_length=2, max_length=100)


class SpeedSet(BaseModel):
    speed: int


class LogLine(BaseModel):
    ts_iso: str
    virtual_iso: str
    level: str
    text: str
