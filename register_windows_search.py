"""
Loki Windows Search & Start Menu Integration
============================================
Creates high-priority Windows Start Menu shortcuts and App Paths registry entries
so that typing 'Loki', 'Loki Trading', or 'Trading Bot' in Windows Search immediately
brings up the Loki Neural Trading Terminal application.
"""
import os
import sys
import winreg
from pathlib import Path
import win32com.client

def install():
    workspace = Path(__file__).parent.resolve()
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)

    script_path = workspace / "loki_desktop.py"
    icon_path = workspace / "loki.ico"

    # Start Menu Programs Directory (Current User - No admin required)
    appdata = os.environ.get("APPDATA", "")
    start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    start_menu.mkdir(parents=True, exist_ok=True)

    # User Desktop Directory
    userprofile = os.environ.get("USERPROFILE", "")
    desktop = Path(userprofile) / "Desktop"

    shell = win32com.client.Dispatch("WScript.Shell")

    # 1. Start Menu: "Loki Neural Terminal"
    lnk1_path = start_menu / "Loki Neural Terminal.lnk"
    s1 = shell.CreateShortcut(str(lnk1_path))
    s1.TargetPath = str(pythonw)
    s1.Arguments = f'"{script_path}"'
    s1.WorkingDirectory = str(workspace)
    s1.Description = "Loki Neural Trading Terminal - Autonomous AI Algorithmic Trading Platform"
    if icon_path.exists():
        s1.IconLocation = f"{icon_path},0"
    s1.Save()
    print(f"Created Start Menu Shortcut: {lnk1_path}")

    # 2. Start Menu: "Loki Trading Bot" (Search alias)
    lnk2_path = start_menu / "Loki Trading Bot.lnk"
    s2 = shell.CreateShortcut(str(lnk2_path))
    s2.TargetPath = str(pythonw)
    s2.Arguments = f'"{script_path}"'
    s2.WorkingDirectory = str(workspace)
    s2.Description = "Loki AI Algorithmic Trading Bot"
    if icon_path.exists():
        s2.IconLocation = f"{icon_path},0"
    s2.Save()
    print(f"Created Start Menu Shortcut: {lnk2_path}")

    # User Desktop Directory (handles OneDrive redirection)
    desktop_dirs = [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "OneDrive - CEDR" / "Desktop",
        Path(os.environ.get("OneDrive", "")) / "Desktop" if os.environ.get("OneDrive") else None,
    ]
    for d in desktop_dirs:
        if d and d.exists():
            desk_path = d / "Loki Neural Terminal.lnk"
            s3 = shell.CreateShortcut(str(desk_path))
            s3.TargetPath = str(pythonw)
            s3.Arguments = f'"{script_path}"'
            s3.WorkingDirectory = str(workspace)
            s3.Description = "Loki Neural Trading Terminal"
            if icon_path.exists():
                s3.IconLocation = f"{icon_path},0"
            s3.Save()
            print(f"Created Desktop Shortcut: {desk_path}")


    # 4. Register in HKCU App Paths (Enables Win+R 'loki' and Windows Search App indexing)
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, str(pythonw))
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, str(workspace))
        print("Registered 'loki.exe' in Windows App Paths (Win+R 'loki' ready)")
    except Exception as ex:
        print(f"Note on registry App Paths: {ex}")

    # 5. Notify Shell to refresh Start Menu index
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0)
        print("Notified Windows Shell of new Start Menu applications.")
    except Exception:
        pass

    print()
    print("SUCCESS: Loki Neural Trading Terminal is now integrated into Windows Search!")
    print("You can now open Windows Start Menu, type 'Loki', and launch the application directly.")

if __name__ == "__main__":
    install()
