# 组装面向用户的 socai 同步包，并生成 downloads/ 下的 zip 供网站下载
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$srcExe = Join-Path $Root "socai-main\target\release\socai.exe"
$dstDir = Join-Path $Root "socai\bin"
$dstExe = Join-Path $dstDir "socai.exe"
$downloads = Join-Path $Root "downloads"
$zipPath = Join-Path $downloads "xhs-favorites-sync-windows.zip"

if (-not (Test-Path $srcExe)) {
    Write-Host "ERROR: 找不到 $srcExe" -ForegroundColor Red
    Write-Host "请先编译: cd socai-main; cargo build --release --bin socai"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
New-Item -ItemType Directory -Force -Path $downloads | Out-Null

Write-Host "Copy socai.exe -> socai\bin\" -ForegroundColor Cyan
Copy-Item -Force $srcExe $dstExe

$stage = Join-Path $env:TEMP "xhs-favorites-sync-pack"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Copy-Item -Force (Join-Path $Root "socai\sync.py") $stage
Copy-Item -Force (Join-Path $Root "socai\一键同步.bat") $stage
Copy-Item -Force (Join-Path $Root "socai\README.md") $stage
Copy-Item -Force (Join-Path $Root "socai\NOTICE.txt") $stage
New-Item -ItemType Directory -Force -Path (Join-Path $stage "bin") | Out-Null
Copy-Item -Force $dstExe (Join-Path $stage "bin\socai.exe")

if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath -Force
Remove-Item -Recurse -Force $stage

$sizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
Write-Host "OK: $zipPath ($sizeMB MB)" -ForegroundColor Green
Write-Host "Website download URL (API running): http://127.0.0.1:8000/downloads/xhs-favorites-sync-windows.zip"
