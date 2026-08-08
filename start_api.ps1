# Start FastAPI backend
# Usage:
#   .\start_api.ps1
#   .\start_api.ps1 -Restart
#   .\start_api.ps1 -Foreground   # keep API in this window (advanced)
param(
    [switch]$Restart,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".\venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
}

if (Test-Path ".\.env") {
    Get-Content ".\.env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $parts = $_.Split('=', 2)
        if ($parts.Count -eq 2) {
            $k = $parts[0].Trim()
            $v = $parts[1].Trim()
            if ($k) { Set-Item -Path ("Env:" + $k) -Value $v }
        }
    }
}

$apiHost = if ($env:API_HOST) { $env:API_HOST } else { "127.0.0.1" }
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$baseUrl = "http://" + $apiHost + ":" + $apiPort
$healthUrl = $baseUrl + "/api/v1/health"
$pythonExe = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

function Test-ApiHealthy {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Get-PortOwner {
    return Get-NetTCPConnection -LocalPort ([int]$apiPort) -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty OwningProcess
}

if ($Restart) {
    $owner = Get-PortOwner
    if ($owner) {
        Write-Host ("Stopping old process PID " + $owner + " ...") -ForegroundColor Yellow
        Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        # also stop child reload workers if any leftover
        Get-NetTCPConnection -LocalPort ([int]$apiPort) -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
    }
}

if ((-not $Restart) -and (Test-ApiHealthy)) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  API already running (OK)" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ("URL:  " + $baseUrl)
    Write-Host ("Docs: " + $baseUrl + "/docs")
    Write-Host ""
    Write-Host "Next: .\start_web.ps1" -ForegroundColor Cyan
    Write-Host "Force restart: .\start_api.ps1 -Restart" -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

$owner = Get-PortOwner
if ($owner) {
    if (-not (Test-ApiHealthy)) {
        Write-Host ("Port " + $apiPort + " occupied by PID " + $owner + " (health check failed).") -ForegroundColor Red
        Write-Host ("Run: .\start_api.ps1 -Restart")
        exit 1
    }
}

$uviArgs = "-m uvicorn backend.main:app --host $apiHost --port $apiPort"
# --reload in a separate window is fine; skip reload for cleaner background start
if ($Foreground) {
    Write-Host ("Starting API in THIS window: " + $baseUrl) -ForegroundColor Green
    Write-Host "This is normal: the process stays running. Do NOT close this window." -ForegroundColor Yellow
    Write-Host "Open another terminal and run: .\start_web.ps1" -ForegroundColor Cyan
    Write-Host ("Docs: " + $baseUrl + "/docs")
    & $pythonExe -m uvicorn backend.main:app --reload --host $apiHost --port $apiPort
    exit $LASTEXITCODE
}

Write-Host "Starting API in a new window ..." -ForegroundColor Green
$cmd = "Set-Location `"$PSScriptRoot`"; & `"$pythonExe`" -m uvicorn backend.main:app --host $apiHost --port $apiPort"
Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoExit",
    "-Command",
    $cmd
) -WindowStyle Normal

Write-Host "Waiting for API to become healthy ..." -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-ApiHealthy) {
        $ok = $true
        break
    }
    Write-Host ("  ... " + ($i + 1) + "s")
}

Write-Host ""
if ($ok) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  API started successfully" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ("URL:  " + $baseUrl)
    Write-Host ("Docs: " + $baseUrl + "/docs")
    Write-Host ""
    Write-Host "A separate PowerShell window is running the API." -ForegroundColor Yellow
    Write-Host "Keep that window open. You can close THIS window or continue here." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Next step: .\start_web.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} else {
    Write-Host "API did not become healthy in time." -ForegroundColor Red
    Write-Host "Check the other PowerShell window for error logs." -ForegroundColor Red
    exit 1
}