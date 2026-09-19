# Release verification

- Python regression suite: 29 passing tests.
- Production frontend: Vite build successful.
- Frontend lint: successful, no warnings.
- Live API: UK carbon forecast received; preview and impossible-deadline rejection checked.
- Browser: demo creation, accelerated clock, custom preview/submission, mobile layout and Impact navigation checked.
- Browser console: no errors observed during those checks.
- Execution: SHA-256 and matrix workloads completed; SHA-256 proof recomputed successfully.
- Persistence: atomic save/restore and interrupted-job recovery covered by regression tests.

The GitHub Actions smoke script has been updated for the new interface. It requires a fresh isolated backend and is intended for CI. It was not separately executed with Playwright in this local session; browser interactions were checked through the attached browser.

Known limits: one process, local operator access, one reference grid, estimated rather than metered energy, modelled price/renewables, daily-profile replay in accelerated time. See README for the complete methodology and demo walkthrough.

- Windows start.ps1: installed its own environment and started successfully.
- Restart recovery: all four completed jobs retained after a real server restart.
- Animated redesign: rendered, motion toggle checked, browser console clear.
