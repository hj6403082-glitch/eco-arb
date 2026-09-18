"""In-process state. One scheduler, one operator, one screen -- no database."""
from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Dict, List, Optional

from . import config
from .clock import clock, iso, real_now
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
