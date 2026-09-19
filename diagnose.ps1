# ECO-ARB connection diagnostic. Run: .\diagnose.ps1   (or .\diagnose.ps1 -Port 8010)
param([int]$Port = 8000)
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== ECO-ARB diagnostic (port $Port) ===" -ForegroundColor Cyan
Write-Host ""

# 1. Is anything listening?
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $conn) {
    Write-Host "[1] Nothing is listening on port $Port." -ForegroundColor Red
    Write-Host "    -> The server is NOT running. Start it with:  .\start.ps1 -Port $Port"
    Write-Host "    -> If your browser still shows the page, that is a CACHED copy."
    Write-Host "       Press Ctrl+Shift+R to hard-refresh once the server is up."
} else {
    $procId = $conn[0].OwningProcess
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    Write-Host "[1] Port $Port is held by PID $procId ($($proc.ProcessName))" -ForegroundColor Green
    if ($proc.ProcessName -notmatch 'python|uvicorn') {
        Write-Host "    -> That is NOT ECO-ARB. Something else owns this port." -ForegroundColor Yellow
        Write-Host "       Use another port:  .\start.ps1 -Port 8010"
    }
}

# 2. Does the API answer?
Write-Host ""
try {
    $r = Invoke-WebRequest "http://127.0.0.1:$Port/api/state" -UseBasicParsing -TimeoutSec 10
    Write-Host "[2] GET /api/state -> HTTP $($r.StatusCode)" -ForegroundColor Green
    $j = $r.Content | ConvertFrom-Json
    Write-Host "    forecast slots : $($j.grid.forecast.Count)"
    Write-Host "    jobs in queue  : $($j.jobs.Count)"
    Write-Host "    grid source    : $($j.grid.status.source)"
    Write-Host "    live feed      : $($j.grid.status.live)"
    if (-not $j.grid.status.live) {
        Write-Host "    last error     : $($j.grid.status.last_error)" -ForegroundColor Yellow
        Write-Host "    -> Offline fallback curve in use. The app works; say so in your demo."
    }
    Write-Host ""
    Write-Host "    THE BACKEND IS HEALTHY. If the UI says 'Connection interrupted'," -ForegroundColor Green
    Write-Host "    your browser is on the wrong port or showing a cached page." -ForegroundColor Green
    Write-Host "    Open http://127.0.0.1:$Port and press Ctrl+Shift+R." -ForegroundColor Green
} catch {
    Write-Host "[2] GET /api/state FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "    -> Start the server:  .\start.ps1 -Port $Port"
}

# 3. Is the built frontend present and current?
Write-Host ""
if (Test-Path 'frontend/dist/index.html') {
    $age = (Get-Item 'frontend/dist/index.html').LastWriteTime
    Write-Host "[3] frontend/dist built at $age" -ForegroundColor Green
} else {
    Write-Host "[3] frontend/dist is MISSING - the page cannot be served." -ForegroundColor Red
    Write-Host "    -> Rebuild:  .\start.ps1 -Rebuild"
}
Write-Host ""
