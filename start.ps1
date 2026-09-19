param([string]$Python = '', [switch]$Rebuild, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:ECO_ARB_DEMO_MODE = 'scenario'
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    if (-not $Python) {
        $bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
        if (Test-Path $bundled) { $Python = $bundled }
        elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py' }
        else { $Python = 'python' }
    }
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ for Windows is required. Pass -Python with its executable path.' }
    & ./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
if ($Rebuild -or -not (Test-Path 'frontend/dist/index.html')) {
    & npm.cmd ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    & npm.cmd run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
Write-Host "ECO-ARB is starting at http://127.0.0.1:$Port" -ForegroundColor Green
& ./.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $Port --no-access-log
