"""Run every check CI runs, on this machine.

CI on GitHub only fires for pushes authored by a human account; a push made
with an app token deliberately does not trigger a run. That makes the Actions
tab an unreliable place to read this project's health. This is the reliable
one: it runs the same three jobs the CI workflow does -- engine tests, lint and
build, and the end-to-end browser smoke -- and prints a verdict.

    python scripts/verify.py              # everything
    python scripts/verify.py --quick      # skip the browser smoke

Exit code is 0 only when every check passed, so it can gate a commit.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"

GREEN, RED, GREY, CYAN, RESET = "\033[32m", "\033[31m", "\033[90m", "\033[36m", "\033[0m"
if WINDOWS and not os.getenv("WT_SESSION"):  # old consoles render the codes literally
    GREEN = RED = GREY = CYAN = RESET = ""

results: list[tuple[str, bool]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok))
    mark = f"{GREEN}  PASS{RESET}" if ok else f"{RED}  FAIL{RESET}"
    print(f"{mark}  {name}")
    if detail:
        for line in detail.strip().splitlines()[:12]:
            print(f"{GREY}        {line}{RESET}")
    return ok


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def npm() -> str:
    """npm is a .cmd shim on Windows, which subprocess will not resolve alone."""
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, seconds: int = 45) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                if res.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    return False


def last_line_matching(text: str, needle: str) -> str:
    hits = [ln.strip() for ln in text.splitlines() if needle in ln]
    return hits[-1] if hits else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the browser smoke suite")
    args = ap.parse_args()

    commit = run(["git", "rev-parse", "--short", "HEAD"], ROOT)[1].strip()
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], ROOT)[1].strip()
    print(f"\n{CYAN}ECO-ARB verification{RESET}")
    print(f"{GREY}commit {commit}  branch {branch}{RESET}\n")

    python = sys.executable

    print(f"{CYAN}Decision engine tests{RESET}")
    code, out = run([python, "-m", "pytest", "backend/tests", "-q"], ROOT)
    record("Backend test suite", code == 0,
           last_line_matching(out, "passed") or out if code else last_line_matching(out, "passed"))

    print(f"\n{CYAN}Lint and build{RESET}")
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").exists():
        print(f"{GREY}        installing frontend dependencies...{RESET}")
        run([npm(), "ci"], frontend)
    code, out = run([npm(), "run", "lint"], frontend)
    record("Frontend lint", code == 0, "no findings" if code == 0 else out)
    code, out = run([npm(), "run", "build"], frontend)
    record("Frontend build", code == 0,
           last_line_matching(out, "built in") if code == 0 else out)

    if args.quick:
        print(f"\n{GREY}Browser smoke skipped (--quick){RESET}")
    else:
        print(f"\n{CYAN}End-to-end smoke{RESET}")
        api_port, ui_port = free_port(), free_port()
        state = Path(tempfile.mkdtemp(prefix="eco-arb-verify-"))
        env = {**os.environ, "ECO_ARB_STATE": str(state / "state.json"),
               "ECO_ARB_DEMO_MODE": "scenario"}
        api = subprocess.Popen(
            [python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(api_port)],
            cwd=ROOT / "backend", env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ui = subprocess.Popen(
            [npm(), "run", "dev", "--", "--port", str(ui_port), "--strictPort",
             "--host", "127.0.0.1"],
            cwd=frontend, env={**env, "VITE_API_BASE": f"http://127.0.0.1:{api_port}"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            up = (wait_for(f"http://127.0.0.1:{api_port}/api/health")
                  and wait_for(f"http://127.0.0.1:{ui_port}/"))
            if not up:
                record("Smoke suite", False, "backend or dev server did not start")
            else:
                code, out = run(["node", "scripts/smoke.mjs"], ROOT,
                                env={**env, "SMOKE_API": f"http://127.0.0.1:{api_port}",
                                     "SMOKE_UI": f"http://127.0.0.1:{ui_port}"})
                if code != 0 and "Executable doesn't exist" in out:
                    # A missing browser is a setup gap, not a broken build, and
                    # the fix is one command rather than a code change.
                    out = ("Playwright has no browser installed. Run:\n"
                           "    npx playwright install chromium\n"
                           "or set PLAYWRIGHT_CHROMIUM to an existing binary.")
                record("Smoke suite", code == 0,
                       f"{out.count('PASS:')} checks passed in a real browser"
                       if code == 0 else out)
        finally:
            for proc in (ui, api):
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            shutil.rmtree(state, ignore_errors=True)

    failed = [name for name, ok in results if not ok]
    print()
    if failed:
        print(f"{RED}{len(failed)} of {len(results)} checks FAILED{RESET}")
        for name in failed:
            print(f"{RED}  - {name}{RESET}")
        return 1
    print(f"{GREEN}ALL {len(results)} CHECKS PASSED{RESET}")
    print(f"{GREY}" + ("Engine tests, lint and build. The browser smoke was skipped."
                       if args.quick else
                       "The same set the CI workflow runs.") + f"{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
