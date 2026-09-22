# Project map

- `frontend/src/App.jsx`: control room, forecast, queue, composer, impact and activity.
- `frontend/src/index.css`: responsive visual system.
- `frontend/src/lib/api.js`: API client with timeout/error handling.
- `backend/app/main.py`: HTTP API and production frontend serving.
- `backend/app/engine.py`: duration-weighted carbon optimization.
- `backend/app/carbon.py`: public forecast ingestion and labelled fallback.
- `backend/app/scheduler.py`: automatic dispatch and lifecycle.
- `backend/app/executor.py`: real bounded CPU workloads and verifiable output.
- `backend/app/store.py`: atomic local persistence and completed-job accounting.
- `backend/tests`: 42 regression and intelligence tests.
- `start.cmd`, `start.ps1`, `start.sh`: single-server launchers; `start.cmd` avoids PowerShell execution-policy issues.
- `backend/app/regions.py`: labelled UK/India feeds, imports and synthetic scenario.
- `backend/app/learning.py`: chronological seasonal regression and validation report.
- `README.md`: setup, demo, architecture and honest limitations.
- `VERIFICATION.md`: checks performed.

Original unused frontend components, static demo HTML and screenshot are retained as legacy reference. The current application is built from App.jsx.
