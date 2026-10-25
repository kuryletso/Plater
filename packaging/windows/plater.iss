; Inno Setup script for Plater's Windows installer. scripts/build_app.py compiles it after PyInstaller 
; and passes the version: ISCC /DAppVersion=1.0.0 packaging\windows\plater.iss
; Paths are relative to this file


#ifndef AppVersion
    #define AppVersion "0.0.0"
#endif

[Setup]
; AppId should never be changed, it's used by updates to find the installed copy
AppId={{8FF7FC3D-6C1B-4559-96C4-13DC216E3DC1}
AppName=Plater
AppVersion={#AppVersion}
AppPublisher=Oleksandr Kurylets
AppPublisherURL=https://github.com/kuryletso/Plater
; for the current user only, so no administrator rights: {autopf} becomes %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
DefaultDirName={autopf}\Plater
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Plater.exe
SetupIconFile=..\..\build\plater.ico
; a fixed name so "latest release" download link always finds the newst one
OutputDir=..\..\dist
OutputBaseFilename=Plater-Setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; an update replaces the libraries whole, so none of the old version's linger
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\Plater\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Plater"; Filename: "{app}\Plater.exe"
Name: "{autodesktop}\Plater"; Filename: "{app}\Plater.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Plater.exe"; Description: "{cm:LaunchProgram,Plater}"; Flags: nowait postinstall skipifsilent