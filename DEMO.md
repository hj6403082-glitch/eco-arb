# ECO-ARB — run it and demo it

## 1. Start it (Windows, one command)

Open **PowerShell** in this folder:

```powershell
.\start.ps1
```

Then open **http://127.0.0.1:8000** in your browser.

That single command builds everything and serves the whole app — frontend and
backend — on one port. **The first run takes 1–3 minutes** (it installs Python
and npm packages). Every run after that starts in about 3 seconds.

Stop it with **Ctrl+C** in the PowerShell window.

### If something goes wrong

| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | `powershell -ExecutionPolicy Bypass -File .\start.ps1` |
| Page looks stale after a code change | `.\start.ps1 -Rebuild` |
| Port 8000 already in use | `.\start.ps1 -Port 8010` → open `http://127.0.0.1:8010` |
| `Python 3.10+ for Windows is required` | Install Python from python.org, tick **Add to PATH**, reopen PowerShell |
| Frontend build fails on native bindings | `rmdir /s /q frontend\node_modules` then `.\start.ps1 -Rebuild` |

On macOS or Linux the equivalent is `./start.sh`.

## 2. The no-fail backup

Double-click **`demo/eco-arb-terminal.html`**.

One self-contained file. No server, no install, no internet. Same optimizer,
same maths as the backend. If the laptop, the venv, or the wifi betrays you five
minutes before your slot, open this and demo anyway.

**Put this file on a USB stick.** It is the single best thing you can do to
de-risk the day.

## 3. Ten minutes before you present

1. **Start the app** and leave it running. Don't start it in front of the judges.
2. **Check the data badge** in the top-right of the page:
   - **"Live"** → you're on the real National Grid feed. Ideal.
   - **"Offline fallback"** → no internet reached the API. Still fine, but say so:
     *"We're on our offline curve right now — the live feed needs open internet
     and conference wifi is blocking it. The maths is identical."* Never let a
     judge notice it before you mention it.
3. **Reset the queue** so you start clean — delete `backend\data\state.json`,
   then restart. (The app persists the queue across restarts on purpose; that's
   a feature, but not what you want at the start of a demo.)
4. **Have the browser already open** at `http://127.0.0.1:8000`, zoomed so the
   forecast chart and the decision panel are both visible.

## 4. The three-beat demo

**Beat 1 — Submit a workload.** Click **New workload**. Name it something real
(`nightly-build`), energy `9` kWh, duration `45` minutes, deadline `12` hours.

The engine comes back with **WAIT** and a window shaded on the forecast curve.

> Look at the scheduled start time. It is usually **not** on a clean half-hour
> boundary — you'll see something like `02:45`. Point at it. That is the
> end-aligned optimum a naive scheduler literally cannot find, and it's the
> difference between 44% saved and 0% saved. It is the single most impressive
> detail on the screen.

**Beat 2 — Hit 360×.** The clock and grid feed compress; the forecast scrolls
and the plan re-evaluates live. Say out loud that time compression speeds up the
clock and the grid, **not** the workload — that still runs at real speed.

**Beat 3 — Open the receipt.** Chained SHA-256 over the actual work, Merkle
root, `independently_verified: true`. The job really ran.

There's also a **Load demo** button that populates a realistic queue instantly,
if you'd rather not type during your slot.

## 5. What to say

See **PITCH.md** — the full script, the optimality proof, and the answer to
"how do you know that's actually the best window?"
