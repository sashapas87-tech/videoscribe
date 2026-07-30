; Inno Setup script for VideoScribe
; Build: ISCC.exe installer.iss  (expects PyInstaller output in dist\VideoScribe)

#define MyAppName "VideoScribe"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppExeName "VideoScribe.exe"

[Setup]
AppId={{7C1E7C1A-5B7A-4B7E-9E1F-2A4D8C6E5B3F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=VideoScribe
DefaultDirName={localappdata}\{#MyAppName}
DisableProgramGroupPage=yes
; Установка без прав администратора (в профиль пользователя)
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=VideoScribe-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\VideoScribe\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
