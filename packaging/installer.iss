; Inno Setup script for the schemagen desktop app. build.ps1 runs: iscc /DAppVersion=<version> packaging\installer.iss
; Per-user install (no admin) into %LOCALAPPDATA%\Programs\schemagen. User data (%LOCALAPPDATA%\schemagen: projects, logs,
; settings) is a different folder and survives uninstall and upgrades.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#if FileExists(AddBackslash(SourcePath) + "assets\icon.ico")
  #define AppIcon "assets\icon.ico"
#else
  #define AppIcon "build\assets\icon.ico"   ; temporary black-and-white icon until stream C's lands (schemagen.spec writes it)
#endif

[Setup]
AppId={{6F1C2B7E-3D4A-4C59-9E21-5B7A0C8D4E13}
AppName=schemagen
AppVersion={#AppVersion}
AppVerName=schemagen {#AppVersion}
AppPublisher=schemagen contributors
AppPublisherURL=https://github.com/andrejbosnjakk/schema-gen
DefaultDirName={localappdata}\Programs\schemagen
DefaultGroupName=schemagen
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
SetupIconFile={#AppIcon}
UninstallDisplayIcon={app}\schemagen.exe
UninstallDisplayName=schemagen
OutputDir=dist
OutputBaseFilename=schemagen-setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "build\app\schemagen\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"
Source: "licences\THIRD_PARTY.txt"; DestDir: "{app}"

[InstallDelete]
; an upgrade replaces the bundle as a whole, so no stale modules from the previous version stay behind
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{userprograms}\schemagen"; Filename: "{app}\schemagen.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\schemagen"; Filename: "{app}\schemagen.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\schemagen.exe"; Description: "{cm:LaunchProgram,schemagen}"; Flags: nowait postinstall skipifsilent
