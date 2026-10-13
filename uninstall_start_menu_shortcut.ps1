# Uninstall LOKI Trading Terminal from Windows Start Menu
# Run this script to remove LOKI from Windows Start Menu

$ErrorActionPreference = "Stop"

Write-Host "Removing LOKI Neural Trading Terminal from Windows Start Menu..." -ForegroundColor Cyan

# Get the Start Menu Programs folder
$StartMenuPrograms = [Environment]::GetFolderPath("StartMenu")
$LokiFolder = Join-Path $StartMenuPrograms "LOKI Trading Terminal"

# Check if folder exists
if (-not (Test-Path $LokiFolder)) {
    Write-Host "LOKI folder not found in Start Menu." -ForegroundColor Yellow
    Write-Host "It may have already been removed." -ForegroundColor Yellow
    exit 0
}

# Remove the folder
Remove-Item -Path $LokiFolder -Recurse -Force

Write-Host "Removed Start Menu folder: $LokiFolder" -ForegroundColor Green

Write-Host ""
Write-Host "SUCCESS! LOKI Neural Trading Terminal has been removed from your Start Menu." -ForegroundColor Green
Write-Host ""
