# Keep this machine awake while running the trading bot

This document explains safe, temporary ways to prevent your laptop from sleeping while you run the trading bot locally. It contains cross-platform commands and small scripts you can run. Use these only while you're actively testing — do not permanently disable sleep on battery-powered devices.

macOS (recommended for mac users)
---------------------------------
- Use the built-in caffeinate tool:
  - Prevent sleep until you stop the command:
    ```bash
    caffeinate -dims &
    # To stop: kill the caffeinate process (e.g., `pkill caffeinate`) or close the terminal
    ```
  - Explanation: -d (prevent display sleep), -i (prevent idle sleep), -m (prevent disk idle), -s (prevent system sleep)

Linux (systemd)
----------------
- Use systemd-inhibit (recommended on systemd-based distros):
  ```bash
  # Blocks suspend/idle while the command runs
  systemd-inhibit --what=idle --why="Keep trading bot awake for testing" bash -c 'while true; do sleep 3600; done'
  # Stop by pressing Ctrl+C in the terminal where it runs or kill the process
  ```
- Alternatively (X11-based desktops):
  ```bash
  # Disable screensaver & DPMS for the session
  xset s off
  xset -dpms
  xset s noblank
  # Re-enable later with: xset s on; xset +dpms
  ```

Windows (PowerShell)
--------------------
- Temporary approach using PowerShell to set AC power timeouts (run as Administrator if required):
  ```powershell
  # Disable sleep while plugged in (AC). Adjust for DC if needed but avoid long battery drain.
  powercfg /change standby-timeout-ac 0
  powercfg /change monitor-timeout-ac 0
  # To restore (example: set standby to 30 minutes):
  # powercfg /change standby-timeout-ac 30
  ```
- Another approach is to run a small PowerShell loop that simulates activity (works without changing system power settings):
  ```powershell
  while ($true) { [System.Windows.Forms.SendKeys]::SendWait('{F15}'); Start-Sleep -Seconds 60 }
  # Note: may require running PowerShell with STA mode and adding Windows Forms assembly
  ```

Safer recommendations
---------------------
- Prefer running your long experiments on a server or cloud VM which is designed to be always-on (Render, Fly, AWS, DigitalOcean). This avoids battery drain and risks to your laptop.
- If you must use your laptop, keep it plugged into power and monitor temperature.
- Use the caffeinate/systemd-inhibit approaches — they are simple to stop when you're done.

Scripts included in this repository
----------------------------------
- `scripts/keep_awake.sh` — systemd-inhibit wrapper (Linux/macOS where available).

Use responsibly and stop the keep-awake process when testing is done.
