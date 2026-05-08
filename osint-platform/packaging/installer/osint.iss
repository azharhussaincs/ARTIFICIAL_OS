; OSINT Platform — Inno Setup installer
; Compile with: iscc osint.iss
;
; Notes:
; - AppId is a STABLE GUID. Never change it: future builds use the same id
;   so Inno treats them as upgrades and preserves user data.
; - User data lives in %LOCALAPPDATA%\OSINT and is intentionally NOT touched
;   by uninstall. Users can wipe it manually.
; - LZMA2 ultra64 is used because the largest payload is the ES snapshot
;   (binary, mostly incompressible) plus ES JDK and bundled Python — solid
;   compression still saves ~600 MB on a typical build.

#define AppName       "OSINT Platform"
#define AppPublisher  "OSINT"
#define AppVersion    "1.0.0"
#define AppExe        "OSINT.exe"
#define AppId         "{{A4F0B1C0-5A3D-4F3E-9C2D-OSINT0000001}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\OSINT
DefaultGroupName=OSINT Platform
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=Output
OutputBaseFilename=OSINT-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
#if FileExists(AddBackslash(SourcePath) + "..\assets\osint.ico")
SetupIconFile=..\assets\osint.ico
#endif
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
CloseApplications=yes
RestartApplications=no
DisableReadyPage=no
ChangesAssociations=no
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; \
    Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; Entire dist tree built by build.bat, including:
;   OSINT.exe, _internal\, elasticsearch\ (with bundled JDK), es-snapshot\,
;   portable.flag.template
Source: "..\dist\OSINT\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OSINT Platform"; Filename: "{app}\{#AppExe}"; \
    IconFilename: "{app}\{#AppExe}"
Name: "{group}\Uninstall OSINT Platform"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OSINT Platform"; Filename: "{app}\{#AppExe}"; \
    IconFilename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; \
    Description: "Launch {#AppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove only state created inside {app}. Userdata in %LOCALAPPDATA%\OSINT
; is intentionally preserved across uninstall/update.
Type: filesandordirs; Name: "{app}\elasticsearch\logs"
Type: filesandordirs; Name: "{app}\elasticsearch\data"
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
function NeedsAddPath(Param: string): boolean;
begin
  Result := False;
end;

procedure InitializeWizard();
begin
  WizardForm.Caption := 'OSINT Platform Setup';
end;

function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
                 '{#AppId}_is1';
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString',
                             sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString',
                        sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := GetUninstallString() <> '';
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  Uninstall: String;
begin
  Result := True;
  if IsUpgrade() then
  begin
    Uninstall := RemoveQuotes(GetUninstallString());
    Exec(Uninstall, '/SILENT /NORESTART /SUPPRESSMSGBOXES',
         '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
