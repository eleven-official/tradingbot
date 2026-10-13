# Install LOKI Trading Terminal to Windows Start Menu
# Run this script as Administrator to add LOKI to Windows Start Menu

$ErrorActionPreference = "Stop"

Write-Host "Installing LOKI Neural Trading Terminal to Windows Start Menu..." -ForegroundColor Cyan

# Get the script directory (assumes this is in the tradingbot folder)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppPath = Join-Path $ScriptDir "loki_desktop.py"
$LauncherPath = Join-Path $ScriptDir "LOKI_LAUNCHER.bat"

# Verify files exist
if (-not (Test-Path $AppPath)) {
    Write-Host "ERROR: loki_desktop.py not found at $AppPath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $LauncherPath)) {
    Write-Host "ERROR: LOKI_LAUNCHER.bat not found at $LauncherPath" -ForegroundColor Red
    exit 1
}

# Get the Start Menu Programs folder
$StartMenuPrograms = [Environment]::GetFolderPath("StartMenu")
$LokiFolder = Join-Path $StartMenuPrograms "LOKI Trading Terminal"

# Create LOKI folder in Start Menu
if (-not (Test-Path $LokiFolder)) {
    New-Item -ItemType Directory -Path $LokiFolder -Force | Out-Null
    Write-Host "Created Start Menu folder: $LokiFolder" -ForegroundColor Green
}

# Create shortcut
$WshShell = New-Object -ComObject WScript.Shell
$ShortcutPath = Join-Path $LokiFolder "LOKI Neural Terminal.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $LauncherPath
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = "LOKI Neural Trading Terminal v5.0 - Paper Trading Workstation"
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
$Shortcut.Save()

Write-Host "Created shortcut: $ShortcutPath" -ForegroundColor Green

# Create uninstall shortcut
$UninstallShortcutPath = Join-Path $LokiFolder "Uninstall LOKI.lnk"
$UninstallShortcut = $WshShell.CreateShortcut($UninstallShortcutPath)
$UninstallShortcut.TargetPath = "powershell.exe"
$UninstallShortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\uninstall_start_menu_shortcut.ps1`""
$UninstallShortcut.WorkingDirectory = $ScriptDir
$UninstallShortcut.Description = "Remove LOKI from Start Menu"
$UninstallShortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,27"
$UninstallShortcut.Save()

Write-Host "Created uninstall shortcut" -ForegroundColor Green

Write-Host ""
Write-Host "SUCCESS! LOKI Neural Trading Terminal has been added to your Start Menu." -ForegroundColor Green
Write-Host "You can now search for 'LOKI' in Windows Start." -ForegroundColor Cyan
Write-Host ""
Write-Host "To remove LOKI from Start Menu, run 'Uninstall LOKI' from the LOKI folder." -ForegroundColor Yellow
