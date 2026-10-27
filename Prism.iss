; Prism Player – Windows installer (Inno Setup 6)
; Built by build_exe.py after the EXE, or by hand: ISCC.exe Prism.iss

#ifndef AppVersion
  #define AppVersion "3.0"
#endif

[Setup]
AppId={{6E0C2F4B-8A51-4D7E-9B3C-2F1A7D5E9C40}
AppName=Prism
AppVersion={#AppVersion}
AppVerName=Prism {#AppVersion}
AppPublisher=Prism
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Prism
DefaultGroupName=Prism
DisableProgramGroupPage=yes
; Per-user by default (no admin prompt, matches the per-user file registration); "all users" on request
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=Prism-Setup-{#AppVersion}
SetupIconFile=prism.ico
UninstallDisplayIcon={app}\Prism.exe
UninstallDisplayName=Prism
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Created by main.py while the player runs
AppMutex=Prism.Player.Running
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associate"; Description: "Hozzáadás a Windowshoz (Társítás menü, alapértelmezett alkalmazások)"; GroupDescription: "Fájltársítás:"

[Files]
; Folder build: Prism.exe, _internal\ (Python, Qt) and LibVLC (libvlc*.dll, plugins\)
Source: "dist\Prism\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Leftovers of older versions' libraries, so an update doesn't mix them with the new ones
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
; Same AppUserModelID as the running player, so a pinned shortcut and the window share one taskbar button
Name: "{autoprograms}\Prism"; Filename: "{app}\Prism.exe"; AppUserModelID: "Prism.Player"
Name: "{autodesktop}\Prism"; Filename: "{app}\Prism.exe"; AppUserModelID: "Prism.Player"; Tasks: desktopicon

[Run]
Filename: "{app}\Prism.exe"; Parameters: "--register"; StatusMsg: "Fájltípusok regisztrálása..."; Flags: waituntilterminated; Tasks: associate
Filename: "{app}\Prism.exe"; Description: "{cm:LaunchProgram,Prism}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\Prism.exe"; Parameters: "--unregister"; Flags: waituntilterminated; RunOnceId: "Unregister"

[UninstallDelete]
Type: files; Name: "{localappdata}\Prism\prism.png"
Type: dirifempty; Name: "{localappdata}\Prism"
