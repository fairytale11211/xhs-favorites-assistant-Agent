# Start Streamlit frontend (run start_api.ps1 first)
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

if (-not $env:API_URL) { $env:API_URL = "http://127.0.0.1:8000" }

# Bypass VPN / Clash local proxy for localhost (critical when VPN is on)
$env:NO_PROXY = "127.0.0.1,localhost,::1"
$env:no_proxy = "127.0.0.1,localhost,::1"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:all_proxy = ""

Write-Host ("Checking API " + $env:API_URL + "/api/v1/health ...") -ForegroundColor Cyan
try {
    # Use .NET WebClient with no proxy for health check
    $wc = New-Object System.Net.WebClient
    $wc.Proxy = $null
    $content = $wc.DownloadString($env:API_URL + "/api/v1/health")
    Write-Host ("API OK: " + $content) -ForegroundColor Green
} catch {
    Write-Host "WARNING: API not reachable. Run .\start_api.ps1 first (keep its window open)." -ForegroundColor Yellow
    Write-Host ("Detail: " + $_.Exception.Message) -ForegroundColor Yellow
}

Write-Host "Starting Streamlit ..." -ForegroundColor Green
Write-Host "If login page says cannot connect: hard-refresh the browser (Ctrl+F5)." -ForegroundColor Cyan
python -m streamlit run app.py