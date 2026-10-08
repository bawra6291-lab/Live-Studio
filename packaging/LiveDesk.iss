; Bundled runtime is separate from the updater-managed app directory.
[Setup]
AppId={{560C967D-2D3E-45E9-981A-48F55DF047E6}
AppName=Live Desk Pilot
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\LiveDeskPilot
DefaultGroupName=Live Desk Pilot
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Output}
OutputBaseFilename=Live-Desk-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=LiveDeskController-v1
CloseApplications=no
DisableProgramGroupPage=yes
UninstallDisplayName=Live Desk Pilot
InfoBeforeFile=INSTALL-NOTICE.txt
[Files]
Source: "{#Stage}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\runtime-dependencies.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\RUNTIME-NOTICE.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Live Desk"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-E -s ""{app}\app\desktop_start.py"""; WorkingDir: "{app}\app"
Name: "{userdesktop}\Live Desk"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-E -s ""{app}\app\desktop_start.py"""; WorkingDir: "{app}\app"
[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-E -s ""{app}\app\desktop_start.py"""; WorkingDir: "{app}\app"; Description: "Open Live Desk"; Flags: nowait postinstall skipifsilent
