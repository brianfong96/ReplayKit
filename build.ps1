<#
.SYNOPSIS
    Build ReplayKit into a standalone Windows executable.
.DESCRIPTION
    Installs dependencies and runs PyInstaller to produce dist\ReplayKit.exe.
.EXAMPLE
    .\build.ps1
#>
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Clean) {
    Write-Host "Cleaning build artifacts..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, *.spec
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

Write-Host "Building ReplayKit.exe..." -ForegroundColor Cyan
pyinstaller `
    --onefile `
    --windowed `
    --name "ReplayKit" `
    --clean `
    replay_kit.py

if (Test-Path "dist\ReplayKit.exe") {
    $size = [math]::Round((Get-Item "dist\ReplayKit.exe").Length / 1MB, 1)
    Write-Host "`nBuild succeeded! dist\ReplayKit.exe ($size MB)" -ForegroundColor Green
} else {
    Write-Host "`nBuild failed — exe not found." -ForegroundColor Red
    exit 1
}
