"""Small supervised seasonal regression with a strictly chronological holdout.

No ML runtime is required. Ridge least squares learns harmonic coefficients
from observations; provider forecasts are never used as observed labels.
"""
import math
import json
import os
from pathlib import Path
import threading
from datetime import timedelta

import httpx

from .fsutil import write_json_atomic
from .clock import iso, parse_iso, real_now


def features(when):
    hour = when.hour + when.minute / 60
    out = [1.0]
    for harmonic in (1, 2, 3):
        angle = 2 * math.pi * harmonic * hour / 24
        out.extend((math.sin(angle), math.cos(angle)))
    return out


def solve(matrix, values):
    """Gaussian elimination with partial pivoting on a small ridge system."""
    a = [list(row) + [value] for row, value in zip(matrix, values)]
    n = len(values)
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(a[r][i]))
        a[i], a[pivot] = a[pivot], a[i]
        scale = a[i][i]
        if abs(scale) < 1e-12:
            raise ValueError("Training matrix is singular")
        a[i] = [v / scale for v in a[i]]
        for r in range(n):
            if r != i:
                factor = a[r][i]
                a[r] = [x - factor * y for x, y in zip(a[r], a[i])]
    return [row[-1] for row in a]


def fit(rows):
    xs = [features(parse_iso(r["timestamp"])) for r in rows]
    ys = [r["intensity"] for r in rows]
    n = len(xs[0])
    matrix = [[sum(x[i] * x[j] for x in xs) + (0.1 if i == j and i else 0)
               for j in range(n)] for i in range(n)]
    values = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(n)]
    return solve(matrix, values)


def predict(coefficients, when):
    return max(0.0, min(1500.0, sum(c * x for c, x in zip(coefficients, features(when)))))


def synthetic_history():
    """Explicit training fixture; validates software, not real forecast accuracy."""
    end = real_now().replace(minute=0, second=0, microsecond=0)
    rows = []
    for i in range(14 * 48):
        when = end - timedelta(minutes=30 * (14 * 48 - i))
        hour = when.hour + when.minute / 60
        value = 210 + 75 * math.sin(2 * math.pi * (hour - 11) / 24)
        value += 24 * math.cos(4 * math.pi * hour / 24) + 8 * math.sin(i * 1.71)
        rows.append({"timestamp": iso(when), "intensity": value})
    return rows


class LearnedForecast:
    def __init__(self, path=None):
        self.lock = threading.RLock()
        self.coefficients = None
        self.report = {"trained": False, "algorithm": "seasonal ridge regression"}
        self.path = path
        if path and path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.coefficients, self.report = saved["coefficients"], saved["report"]

    def train(self, rows, dataset):
        rows = sorted(rows, key=lambda r: parse_iso(r["timestamp"]))
        if len(rows) < 192:
            raise ValueError("At least four days of half-hour observations are required")
        seen = set()
        for r in rows:
            stamp = parse_iso(r["timestamp"])
            if stamp in seen or not math.isfinite(r["intensity"]) or not 0 <= r["intensity"] <= 1500:
                raise ValueError("History contains duplicate timestamps or invalid intensities")
            seen.add(stamp)
        split = len(rows) - 48
        train, test = rows[:split], rows[split:]
        weights = fit(train)
        errors = [abs(predict(weights, parse_iso(r["timestamp"])) - r["intensity"]) for r in test]
        by_stamp = {parse_iso(r["timestamp"]): r["intensity"] for r in train}
        baseline = [by_stamp.get(parse_iso(r["timestamp"]) - timedelta(days=1), train[-1]["intensity"])
                    for r in test]
        baseline_mae = sum(abs(p - r["intensity"]) for p, r in zip(baseline, test)) / len(test)
        mae = sum(errors) / len(errors)
        report = {
            "trained": True, "algorithm": "seasonal ridge regression", "dataset": dataset,
            "train_samples": len(train), "test_samples": len(test),
            "holdout": "last 48 available observations, chronological; no refit before evaluation",
            "mae_gco2_kwh": round(mae, 3), "baseline_mae_gco2_kwh": round(baseline_mae, 3),
            "baseline": "previous day at the same half-hour; last training value if unavailable",
            "beats_baseline": mae < baseline_mae, "trained_at": iso(real_now()),
            "training_end": train[-1]["timestamp"], "validation_start": test[0]["timestamp"],
            "observations_end": rows[-1]["timestamp"],
            "residual_p90_gco2_kwh": round(sorted(errors)[int(.9 * (len(errors) - 1))], 3),
            "uncertainty_note": "Historical validation residual, not a calibrated prediction interval",
            "scope": "GB national only; no transfer to Indian regions",
        }
        # Refit on all available observations only after the holdout evaluation.
        final_weights = fit(rows)
        with self.lock:
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(self.path, {"coefficients": final_weights, "report": report},
                                  label="trained model")
            self.coefficients, self.report = final_weights, report
        return self.status()

    def status(self):
        with self.lock:
            return dict(self.report)

    def intensity(self, when):
        with self.lock:
            if self.coefficients is None:
                raise ValueError("Train the model before choosing learned forecasts")
            return predict(self.coefficients, when)

    def train_public(self):
        end = real_now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        start = end - timedelta(days=14)
        url = f"https://api.carbonintensity.org.uk/intensity/{iso(start)}/{iso(end)}"
        response = httpx.get(url, timeout=25)
        response.raise_for_status()
        rows = [{"timestamp": r["from"], "intensity": float(r["intensity"]["actual"])}
                for r in response.json().get("data", [])
                if (r.get("intensity") or {}).get("actual") is not None]
        return self.train(rows, "public UK historical actual intensity")


learned = LearnedForecast(Path(os.getenv("ECO_ARB_STATE", Path(__file__).resolve().parents[1] / "data" / "state.json")).with_name("model.json"))
