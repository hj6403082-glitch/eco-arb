# ECO-ARB — judging pitch

**One line:** ECO-ARB moves deferrable compute to the cleanest half-hour the grid
will offer before your deadline, and proves the work actually ran.

---

## The 60-second version

Every batch job — a nightly build, a model fine-tune, a report render — has a
deadline, not a start time. Nobody cares *when* it runs, only that it's done by
morning. But we run it the instant it's submitted, on whatever electricity
happens to be in the wires.

UK grid carbon intensity swings between roughly 60 and 350 gCO₂/kWh across a
single day. Same job, same energy, four to five times the emissions depending on
the hour you pick.

ECO-ARB takes the National Grid's 24-hour forecast, finds the cleanest feasible
window before your deadline, and schedules the job there. Then it runs the job
for real and hands you a cryptographic receipt.

---

## The three things to demo

1. **Submit a job.** Watch the decision come back: RUN or WAIT, with the window
   highlighted on the forecast curve and a plain-English reason.
2. **Hit 360×.** The clock and the grid feed compress; the forecast scrolls, the
   plan re-evaluates every tick. The workload itself still runs at real speed —
   that's the honest part.
3. **Open the receipt.** Chained SHA-256 over the work, Merkle root, and
   `independently_verified: true` from a separate recomputation.

---

## The question you will get asked

> *"How do you know that's actually the best window?"*

This is the one to be ready for, and the answer is now genuinely strong.

**We don't sample. We don't heuristic. We enumerate every window that can be
optimal, and it is provably a finite set.**

Carbon intensity is piecewise-constant — one value per half-hour slot. For a
job of fixed duration D, total carbon as a function of start time `t` is
piecewise-**linear**: it only changes slope when an endpoint of the window
crosses a slot boundary. A piecewise-linear function attains its minimum at a
breakpoint. So the optimum is always at a start time where **either** the start
**or** the end of the window sits on a slot edge — plus "right now" and
"as late as the deadline allows."

That's ~100 candidates for a 24-hour horizon. We score all of them exactly, with
fractional-slot weighting (a 45-minute job is charged 15 minutes of one slot and
30 of the next — not two full half-hours), and take the minimum.

**Why this matters, concretely.** A start-aligned-only search — the obvious
implementation, and what we shipped first — misses real optima:

```
slots:    100, 10, 200, 200, ...  gCO₂/kWh      job: 45 min, 1 kWh
start-aligned best  →  12:00  =  70 gCO₂   (RUN now, 0% saved)
true optimum        →  12:15  =  40 gCO₂   (WAIT 15 min, 43% saved)
```

It straddles the clean slot instead of sitting inside it. We caught this, fixed
it, and pinned it with a regression test
(`test_end_aligned_window_is_considered`). Brute-forcing every minute of the
horizon now agrees with the engine exactly.

If a judge is technical, this is the slide to linger on: *we found a correctness
bug in our own optimizer and can show you the proof that it's gone.*

---

## The honesty slide

Hackathon demos lie. Ours labels itself:

- **Real** — the National Grid forecast, fetched live from
  `api.carbonintensity.org.uk`. Every slot on screen is tagged with whether it
  came from the live feed, a cache, or a modelled extension past the horizon.
- **Derived** — carbon and cost figures, computed from that forecast.
- **Modelled** — energy per job is an operator estimate. The API says so:
  `"energy_basis": "operator estimate; not metered"`. We are not pretending to
  have a power meter.

Time compression is labelled on screen at all times. It compresses the clock and
the grid feed. It does **not** compress the workload — that runs at wall speed,
which is why a 360× demo still takes real seconds to finish a job.

---

## What's actually built

- FastAPI backend, 15 routes, **29 passing tests** including 14 regression tests
- APScheduler dispatch with a worker cap, state checkpointed to disk so a
  restart doesn't lose the queue
- React 19 + Vite frontend, live forecast chart with the chosen window shaded
- Real deferrable workload (`hash_grind`) producing a verifiable hash chain
- End-to-end Playwright smoke test in CI — backend, browser submission,
  navigation, mobile overflow, and zero-runtime-errors, all gated on every push
- Offline fallback curve, so conference wifi cannot kill the demo

---

## If you have 10 extra seconds

> "The scheduler is the easy half. The hard half is being able to stand here and
> tell you exactly which numbers on this screen are measured, which are computed,
> and which are estimated — and we can."
