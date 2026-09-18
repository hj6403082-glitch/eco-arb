"""Real workload execution.

This is the part that is deliberately NOT simulated. When the scheduler says
a job is due, a worker thread burns real CPU and writes a real artifact to
disk whose contents can be checked independently of this process.

Time compression does not reach here. The virtual clock decides *when* a job
starts; once started it runs at real wall-clock speed, so a 360x demo still
shows a genuine multi-second RUNNING state.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict

ARTIFACT_DIR = Path(os.getenv("ECO_ARB_ARTIFACTS", Path(__file__).resolve().parents[1] / "artifacts"))
ProgressFn = Callable[[float], None]


# Work per kWh, tuned so a 10 kWh job burns a few seconds of real CPU -- long
# enough that the RUNNING state is visible on stage, short enough to demo.
# Raise ECO_ARB_WORK_SCALE to make jobs heavier on a faster machine.
WORK_SCALE = float(os.getenv("ECO_ARB_WORK_SCALE", "1.0"))


def _rounds_for(energy_kwh: float) -> int:
    """Bigger jobs really do take longer, within demo-friendly bounds."""
    rounds = 9_000_000 * (energy_kwh / 10.0) * WORK_SCALE
    return int(min(max(rounds, 1_000_000), 30_000_000))


def hash_grind(job, progress: ProgressFn) -> dict:
    """Chained SHA-256 plus a Merkle root over the chain.

    Real, verifiable work: the final digest depends on every round, and
    `verify_hash_grind` recomputes it from the recorded seed.
    """
    rounds = _rounds_for(job.energy_kwh)
    seed = f"{job.id}:{job.name}:{job.energy_kwh}".encode()
    digest = hashlib.sha256(seed).digest()
    leaves = []
    started = time.monotonic()
    step = max(rounds // 100, 1)
    for i in range(rounds):
        digest = hashlib.sha256(digest).digest()
        if i % 4096 == 0:
            leaves.append(digest)
        if i % step == 0:
            progress(i / rounds)
    # Merkle root over the sampled chain
    level = leaves or [digest]
    while len(level) > 1:
        level = [
            hashlib.sha256(level[i] + level[min(i + 1, len(level) - 1)]).digest()
            for i in range(0, len(level), 2)
        ]
    progress(1.0)
    return {
        "workload": "hash_grind",
        "rounds": rounds,
        "seed": seed.decode(),
        "final_digest": digest.hex(),
        "merkle_root": level[0].hex(),
        "leaves_sampled": len(leaves),
        "real_seconds": round(time.monotonic() - started, 3),
    }


def verify_hash_grind(result: dict) -> bool:
    """Independently recompute a hash_grind result from its recorded seed."""
    digest = hashlib.sha256(result["seed"].encode()).digest()
    for _ in range(result["rounds"]):
        digest = hashlib.sha256(digest).digest()
    return digest.hex() == result["final_digest"]


def matrix_train(job, progress: ProgressFn) -> dict:
    """Dense float matrix multiply in pure Python -- a stand-in for the kind
    of batch numeric work a carbon-aware scheduler actually defers."""
    n = int(min(max(360 * (job.energy_kwh / 10.0) ** 0.5 * WORK_SCALE**0.34, 120), 620))
    a = [[((i * 37 + j * 17) % 100) / 100.0 for j in range(n)] for i in range(n)]
    b = [[((i * 11 + j * 53) % 100) / 100.0 for j in range(n)] for i in range(n)]
    started = time.monotonic()
    passes = 3
    checksum = 0.0
    for p in range(passes):
        c = [[0.0] * n for _ in range(n)]
        for i in range(n):
            ai = a[i]
            ci = c[i]
            for k in range(n):
                aik = ai[k]
                bk = b[k]
                for j in range(n):
                    ci[j] += aik * bk[j]
            progress((p * n + i + 1) / (passes * n))
        checksum = sum(sum(row) for row in c)
        a = c
        # renormalise so the checksum stays finite across passes
        scale = max(max(abs(v) for v in row) for row in a) or 1.0
        a = [[v / scale for v in row] for row in a]
    progress(1.0)
    return {
        "workload": "matrix_train",
        "matrix_n": n,
        "passes": passes,
        "flops_approx": 2 * n**3 * passes,
        "checksum": round(checksum, 6),
        "real_seconds": round(time.monotonic() - started, 3),
    }


def shell(job, progress: ProgressFn) -> dict:
    """Execute an actual external command -- the general deferrable job.

    Enabled only when ECO_ARB_SHELL_CMD is set, so an exposed instance cannot
    be turned into a command runner by posting a job.
    """
    cmd = os.getenv("ECO_ARB_SHELL_CMD")
    if not cmd:
        raise RuntimeError(
            "workload 'shell' requires the ECO_ARB_SHELL_CMD environment variable"
        )
    progress(0.05)
    started = time.monotonic()
    proc = subprocess.run(
        shlex.split(cmd), capture_output=True, text=True, timeout=600, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Workload exited with code {proc.returncode}: {proc.stderr[-500:]}")
    progress(1.0)
    return {
        "workload": "shell",
        "command": cmd,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "real_seconds": round(time.monotonic() - started, 3),
    }


WORKLOADS: Dict[str, Callable] = {
    "hash_grind": hash_grind,
    "matrix_train": matrix_train,
}
if os.getenv("ECO_ARB_SHELL_CMD"):
    WORKLOADS["shell"] = shell

pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eco-arb-exec")


def run_job(job, progress: ProgressFn) -> dict:
    fn = WORKLOADS.get(job.workload)
    if fn is None:
        raise ValueError(
            f"unknown workload {job.workload!r}; expected one of {sorted(WORKLOADS)}"
        )
    result = fn(job, progress)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = ARTIFACT_DIR / f"{job.id}.json"
    payload = {
        "job_id": job.id,
        "name": job.name,
        "energy_kwh": job.energy_kwh,
        "deadline_iso": job.deadline_iso,
        "run_at_iso": job.run_at_iso,
        "result": result,
    }
    artifact.write_text(json.dumps(payload, indent=2))
    result["artifact_path"] = str(artifact)
    return result
