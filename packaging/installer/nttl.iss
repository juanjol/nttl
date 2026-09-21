; Inno Setup script for NTTL. Build with:
;   iscc /DAppVersion=0.1.0 packaging\installer\nttl.iss
; It expects the PyInstaller output in build\dist\nttl and icons in build\icons.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "NTTL"
#define AppPublisher "NTTL"
#define AppExeName "nttl-tray.exe"
#define AppUrl "https://github.com/juanjol/nttl"

[Setup]
AppId={{8F2C5A41-3E6B-4C7D-9B84-2A1F6D0E7C35}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppSupportURL={#AppUrl}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=build\installer
OutputBaseFilename=NTTL-{#AppVersion}-Setup
SetupIconFile=build\icons\nttl.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "startup"; Description: "Start NTTL when I sign in"; GroupDescription: "Startup"; Flags: unchecked

[Files]
Source: "build\dist\nttl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} console"; Filename: "{app}\nttl.exe"; Parameters: "--help"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
