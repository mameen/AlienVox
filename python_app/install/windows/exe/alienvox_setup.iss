; AlienVox Windows installer (Inno Setup) — base tier (SAPI5 only, no ML).
;
; Packages the PyInstaller onedir build from
; install\.venv-base-build\build\exe\dist\AlienVox\ into a proper Start
; Menu install with an uninstaller. Requires build_exe.bat to have run
; the PyInstaller freeze step first (it does this automatically before
; invoking ISCC on this script).
;
; Everything transient here — the build venv, the PyInstaller dist/work
; folders, and the compiled installer .exe itself — lives under
; install\.venv-base-build\, one folder already covered by .gitignore's
; ".venv-base-build/" rule.
;
; Compile with the Inno Setup Compiler (ISCC.exe) — free, from
; https://jrsoftware.org/isinfo.php. Not bundled with this repo.

#define MyAppName "AlienVox"
#define MyAppPublisher "AlienTech.Software"
#define MyAppURL "https://alientech.software/"
#define MyAppExeName "AlienVox.exe"
; Version is read from version.yaml at build time by build_exe.bat, which
; passes it via /DMyAppVersion=... — falls back to 0.0.0 if compiled directly.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

; Build output root: install\.venv-base-build\build\exe\ (relative to
; this .iss file, two levels up from install\windows\exe\ to install\).
#define BuildOut "..\..\.venv-base-build\build\exe"
#define DistDir BuildOut + "\dist\AlienVox"

[Setup]
AppId={{B6C1E9D2-4F3A-4B7E-9B9C-ALIENVOXBASE}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; No admin rights required — installs per-user by default, matching the
; app's own philosophy of not touching anything outside its own folder /
; %LOCALAPPDATA%\com.alientech.alienvox.
PrivilegesRequired=lowest
OutputDir={#BuildOut}
OutputBaseFilename=AlienVoxSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#DistDir}\_internal\resources\icons\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardImageFile=wizard_image.bmp,wizard_image_125.bmp
WizardSmallImageFile=wizard_small.bmp,wizard_small_125.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; user.yaml / stacks.yaml overrides and the app's own logs live next to
; the exe (see src/config.py) — remove them on uninstall so a reinstall
; starts clean. Does NOT touch %LOCALAPPDATA%\com.alientech.alienvox
; (model weight cache) — that survives an uninstall deliberately, so
; reinstalling doesn't force re-downloading anything.
Type: filesandordirs; Name: "{app}\.logs"
Type: filesandordirs; Name: "{app}\.generated"
