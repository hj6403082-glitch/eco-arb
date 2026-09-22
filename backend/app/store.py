"""In-process state. One scheduler, one operator, one screen -- no database."""
from __future__ import annotations

import threading
import json
import os
from pathlib import Path
from collections import deque
from typing import Deque, Dict, List, Optional

from . import config
from .clock import clock, iso, real_now
from .fsutil import quarantine, write_json_atomic
from .models import Decision, Job, LogLine


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.jobs: Dict[str, Job] = {}
        self.decisions: Dict[str, Decision] = {}
        # Carbon the job would have emitted had it run the instant it was
        # submitted. Frozen at submission so the saving we report later is
        # measured against a fixed baseline, not a moving one.
        self.baselines: Dict[str, float] = {}
        self.baseline_costs: Dict[str, float] = {}
        self.actual_carbon: Dict[str, float] = {}
        self.actual_cost: Dict[str, float] = {}
        self.logs: Deque[LogLine] = deque(maxlen=config.LOG_RING_SIZE)
        self._seq = 0
        self.path = Path(os.getenv("ECO_ARB_STATE", Path(__file__).resolve().parents[1] / "data" / "state.json"))
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.jobs = {k: Job(**v) for k, v in data.get("jobs", {}).items()}
            self.decisions = {k: Decision(**v) for k, v in data.get("decisions", {}).items()}
            for key in ("baselines", "baseline_costs", "actual_carbon", "actual_cost"):
                setattr(self, key, data.get(key, {}))
            self._seq = data.get("seq", 0)
            self.logs.extend(LogLine(**v) for v in data.get("logs", []))
            for job in self.jobs.values():
                if job.status == "RUNNING":
                    job.status = "FAILED"
                    job.result = {"error": "Execution interrupted by server restart; submit a new workload to retry."}
        except (ValueError, TypeError, OSError, KeyError) as exc:
            # Losing the previous session is an inconvenience; refusing to start
            # is a dead demo. Reset to empty and keep the file for inspection.
            self.jobs, self.decisions, self._seq = {}, {}, 0
            for key in ("baselines", "baseline_costs", "actual_carbon", "actual_cost"):
                setattr(self, key, {})
            self.logs.clear()
            quarantine(self.path, str(exc), label="session state")

    def checkpoint(self):
        with self.lock:
            data = {"seq": self._seq,
                    "jobs": {k: v.model_dump() for k, v in self.jobs.items()},
                    "decisions": {k: v.model_dump() for k, v in self.decisions.items()},
                    "logs": [v.model_dump() for v in self.logs]}
            for key in ("baselines", "baseline_costs", "actual_carbon", "actual_cost"):
                data[key] = getattr(self, key)
            write_json_atomic(self.path, data, label="session state")

    def next_id(self) -> str:
        with self.lock:
            self._seq += 1
            return f"job-{self._seq:03d}"

    def log(self, text: str, level: str = "INFO") -> None:
        with self.lock:
            self.logs.append(
                LogLine(
                    ts_iso=iso(real_now()),
                    virtual_iso=iso(clock.now()),
                    level=level,
                    text=text,
                )
            )

    def add(self, job: Job) -> Job:
        with self.lock:
            self.jobs[job.id] = job
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self.lock:
            return self.jobs.get(job_id)

    def list_jobs(self) -> List[Job]:
        with self.lock:
            return list(self.jobs.values())

    def set_decision(self, decision: Decision) -> None:
        with self.lock:
            self.decisions[decision.job_id] = decision

    def totals(self) -> dict:
        with self.lock:
            saved_g = 0.0
            saved_cost = 0.0
            emitted_g = 0.0
            energy = 0.0
            done = 0
            for job_id, actual in self.actual_carbon.items():
                if job_id not in self.jobs or self.jobs[job_id].status != "DONE":
                    continue
                baseline = self.baselines.get(job_id, actual)
                saved_g += baseline - actual
                emitted_g += actual
                saved_cost += self.baseline_costs.get(job_id, 0.0) - self.actual_cost.get(job_id, 0.0)
                job = self.jobs.get(job_id)
                if job:
                    energy += job.energy_kwh
                    if job.status == "DONE":
                        done += 1
            if abs(saved_g) < 1e-9:
                saved_g = 0.0
            if abs(saved_cost) < 1e-12:
                saved_cost = 0.0
            pct = (saved_g / (saved_g + emitted_g) * 100.0) if (saved_g + emitted_g) > 0 else 0.0
            return {
                "carbon_saved_g": round(saved_g, 1),
                "carbon_emitted_g": round(emitted_g, 1),
                "carbon_saved_pct": round(pct, 2),
                "cost_saved_gbp": round(saved_cost, 4),
                "energy_scheduled_kwh": round(energy, 2),
                "jobs_completed": done,
                "jobs_total": len(self.jobs),
            }


store = Store()
