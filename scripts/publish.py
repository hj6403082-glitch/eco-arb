"""Build the site and publish it to the gh-pages branch.

GitHub Pages can serve either from an Actions run or straight from a branch.
This uses the branch route deliberately: it needs no workflow run, so the site
can be redeployed even when Actions is not creating runs for this repository.

    python scripts/publish.py

The branch is rebuilt from scratch each time and force-pushed -- it holds a
build, not history, and the source history lives on the real branch.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "ecooarb.cv"
BRANCH = "gh-pages"


def run(cmd: list[str], cwd: Path, check: bool = True) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        print(f"\n  failed: {' '.join(cmd)}")
        print((proc.stdout or "") + (proc.stderr or ""))
        sys.exit(1)
    return (proc.stdout or "") + (proc.stderr or "")


def npm() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def main() -> int:
    frontend = ROOT / "frontend"
    dist = frontend / "dist"

    print("Building the site...")
    if not (frontend / "node_modules").exists():
        run([npm(), "ci"], frontend)
    out = run([npm(), "run", "build"], frontend)
    print("  " + next((ln.strip() for ln in out.splitlines() if "built in" in ln), "built"))

    # The standalone single-file demo ships alongside the app so it stays
    # reachable at /demo/ when the app is the site root.
    demo = dist / "demo"
    demo.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "demo" / "eco-arb-terminal.html", demo / "index.html")

    # CNAME pins the custom domain; without it GitHub drops the domain on the
    # next deploy. .nojekyll stops Jekyll mangling Vite's hashed asset names.
    (dist / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (dist / ".nojekyll").write_text("", encoding="utf-8")

    origin = run(["git", "remote", "get-url", "origin"], ROOT).strip()
    source = run(["git", "rev-parse", "--short", "HEAD"], ROOT).strip()

    print(f"Publishing to {BRANCH} ({DOMAIN})...")
    with tempfile.TemporaryDirectory(prefix="eco-arb-publish-") as tmp:
        staged = Path(tmp) / "site"
        shutil.copytree(dist, staged)
        run(["git", "init", "-q"], staged)
        run(["git", "checkout", "-q", "-b", BRANCH], staged)
        run(["git", "add", "-A"], staged)
        run(["git", "commit", "-q", "-m", f"Publish {source} to {DOMAIN}"], staged)
        run(["git", "remote", "add", "origin", origin], staged)
        run(["git", "push", "-q", "--force", "origin", BRANCH], staged)

    print(f"\n  Published {source} to {BRANCH}.")
    print(f"  https://{DOMAIN}/  (and /demo/ for the standalone page)")
    print("  GitHub rebuilds the site within a minute or so.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
