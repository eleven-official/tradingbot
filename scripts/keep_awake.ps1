# PowerShell helper for keeping Windows awake (run in PowerShell)
# Save as scripts\keep_awake.ps1 and run: powershell -ExecutionPolicy Bypass -File .\scripts\keep_awake.ps1

Add-Type -AssemblyName System.Windows.Forms
Write-Host "Starting simple keep-awake loop. Press Ctrl+C to stop."
while ($true) {
    # Send an innocuous non-printing key to keep session active
    [System.Windows.Forms.SendKeys]::SendWait("{F15}")
    Start-Sleep -Seconds 60
}
