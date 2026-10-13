; Loki Trading Platform - NSIS Installer Script
; Requires NSIS 3.0+

!include "MUI2.nsh"
!include "x64.nsh"

; Installer settings
Name "Loki Trading Platform"
OutFile "Loki-Setup.exe"
InstallDir "$PROGRAMFILES64\Loki Trading Platform"
InstallDirRegKey HKLM "Software\LokiTrading\Loki" "Install_Dir"
RequestExecutionLevel admin

; Version information
VIProductVersion "2.0.0.0"
VIAddVersionKey "ProductName" "Loki Trading Platform"
VIAddVersionKey "CompanyName" "Loki Trading Systems"
VIAddVersionKey "LegalCopyright" "Copyright © 2024-2026 Loki Trading Systems"
VIAddVersionKey "FileDescription" "Loki Trading Platform Installer"
VIAddVersionKey "FileVersion" "2.0.0.0"
VIAddVersionKey "ProductVersion" "2.0.0"

; Modern UI settings
!define MUI_ABORTWARNING
!define MUI_ICON "assets\loki_icon.ico"
!define MUI_UNICON "assets\loki_icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "assets\installer_banner.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "assets\installer_header.bmp"
!define MUI_HEADERIMAGE_RIGHT

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; Languages
!insertmacro MUI_LANGUAGE "English"

; Installer sections
Section "Loki Core Application" SecCore
  SectionIn RO ; Required
  
  SetOutPath "$INSTDIR"
  
  ; Main application files
  File /r "dist\loki\*.*"
  File "LICENSE.txt"
  File "README.md"
  
  ; Create directories
  CreateDirectory "$INSTDIR\config"
  CreateDirectory "$INSTDIR\logs"
  CreateDirectory "$INSTDIR\state"
  CreateDirectory "$INSTDIR\data"
  
  ; Write registry keys
  WriteRegStr HKLM "Software\LokiTrading\Loki" "Install_Dir" "$INSTDIR"
  WriteRegStr HKLM "Software\LokiTrading\Loki" "Version" "2.0.0"
  
  ; Write uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
  ; Add to Programs and Features
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "DisplayName" "Loki Trading Platform"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "DisplayIcon" "$INSTDIR\loki.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "Publisher" "Loki Trading Systems"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "DisplayVersion" "2.0.0"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki" "NoRepair" 1
  
SectionEnd

Section "Desktop Shortcut" SecDesktop
  CreateShortcut "$DESKTOP\Loki Trading Platform.lnk" "$INSTDIR\loki.exe" "" "$INSTDIR\loki.exe" 0
SectionEnd

Section "Start Menu Shortcuts" SecStartMenu
  CreateDirectory "$SMPROGRAMS\Loki Trading Platform"
  CreateShortcut "$SMPROGRAMS\Loki Trading Platform\Loki Trading Platform.lnk" "$INSTDIR\loki.exe"
  CreateShortcut "$SMPROGRAMS\Loki Trading Platform\Documentation.lnk" "$INSTDIR\docs\index.html"
  CreateShortcut "$SMPROGRAMS\Loki Trading Platform\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Windows Search Integration" SecSearch
  ; Register for Windows search
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" "" "$INSTDIR\loki.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe" "Path" "$INSTDIR"
SectionEnd

Section "File Associations" SecFileAssoc
  ; Associate .loki strategy files
  WriteRegStr HKCR ".loki" "" "LokiStrategy"
  WriteRegStr HKCR "LokiStrategy" "" "Loki Trading Strategy"
  WriteRegStr HKCR "LokiStrategy\DefaultIcon" "" "$INSTDIR\loki.exe,0"
  WriteRegStr HKCR "LokiStrategy\shell\open\command" "" '"$INSTDIR\loki.exe" "%1"'
SectionEnd

; Section descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "Core application files (required)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Create a desktop shortcut"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} "Create Start Menu shortcuts"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecSearch} "Enable Windows search integration"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFileAssoc} "Associate .loki files with Loki"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; Uninstaller
Section "Uninstall"
  
  ; Remove files
  Delete "$INSTDIR\loki.exe"
  Delete "$INSTDIR\LICENSE.txt"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"
  
  ; Remove shortcuts
  Delete "$DESKTOP\Loki Trading Platform.lnk"
  RMDir /r "$SMPROGRAMS\Loki Trading Platform"
  
  ; Remove registry keys
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Loki"
  DeleteRegKey HKLM "Software\LokiTrading\Loki"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\loki.exe"
  DeleteRegKey HKCR ".loki"
  DeleteRegKey HKCR "LokiStrategy"
  
SectionEnd

; Installation event functions
Function .onInit
  ; Check for 64-bit Windows
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Loki requires 64-bit Windows!"
    Abort
  ${EndIf}
  
  ; Check for administrator privileges
  UserInfo::GetAccountType
  pop $0
  ${If} $0 != "admin"
    MessageBox MB_ICONSTOP "Administrator privileges required!"
    SetErrorLevel 740 ; ERROR_ELEVATION_REQUIRED
    Quit
  ${EndIf}
  
FunctionEnd

Function .onInstSuccess
  MessageBox MB_YESNO "Installation complete! Launch Loki now?" IDYES LaunchNow IDNO NoLaunch
  LaunchNow:
    Exec "$INSTDIR\loki.exe"
  NoLaunch:
FunctionEnd
