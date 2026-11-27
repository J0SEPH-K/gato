; Inno Setup script: wraps dist\Gato (PyInstaller output) into one GatoSetup.exe
#define AppName "GATO"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B0E7C0E-3D1A-4B7E-9C57-6A1E3C1F0A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=J0SEPH-K
DefaultDirName={autopf}\GATO
DefaultGroupName=GATO
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=GatoSetup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\Gato.exe
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; 1.0.20 shipped VERSION as version.dll beside the exe, which shadows the
; system version.dll on case-insensitive NTFS. Drop it on upgrade.
Type: files; Name: "{app}\version.dll"
; Wipe the app dir before copying. [Files] is ignoreversion, so a module a newer
; build DROPPED (renamed, folded elsewhere, deleted) stayed on disk forever and the
; frozen bootloader could still import it - that is how an "updated" PC keeps
; behaving like the old build. Config lives in %LOCALAPPDATA%\GATO, not here.
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "..\dist\Gato\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsVCRedist
; Npcap is what scapy talks to; without wpcap.dll the packet sniffer cannot open a capture.
; /winpcap_mode=yes makes it answer to the WinPcap API names the frozen build links against.
Source: "npcap-installer.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsNpcap

[Icons]
; The desktop icon is the operator's only launch path on the PC, so it is ALWAYS created -
; as a task it was skippable (and skipped on silent updates, which then had no icon at all).
; WorkingDir is pinned because the app resolves VERSION/assets relative to the exe directory.
Name: "{autoprograms}\GATO"; Filename: "{app}\Gato.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\GATO"; Filename: "{app}\Gato.exe"; WorkingDir: "{app}"

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Microsoft Visual C++ runtime..."; Check: NeedsVCRedist; Flags: waituntilterminated
Filename: "{tmp}\npcap-installer.exe"; Parameters: "/S /winpcap_mode=yes"; StatusMsg: "Npcap (packet capture driver)..."; Check: NeedsNpcap; Flags: waituntilterminated
; EXACTLY ONE launch entry. The rule that must never be broken:
;   * an interactive install must NOT launch (the desktop shortcut is how the operator
;     starts it, so a launch here just races the shortcut and the shell);
;   * a silent install (the in-app updater) MUST launch, or the machine is left with the
;     new build on disk and nothing running.
; `postinstall` alone did not hold that line: on /VERYSILENT it can still fire together
; with the unconditional entry, and the two processes then fought over z-order until the
; foreground-steal failures hit the hundreds. Making the first entry silent-only fixes it
; by construction instead of by ordering luck.
Filename: "{app}\Gato.exe"; Description: "{cm:LaunchProgram,GATO}"; Flags: nowait postinstall skipifsilent; Check: WizardSilent
Filename: "{app}\Gato.exe"; Flags: nowait; Check: WizardSilent

[Code]
function NeedsNpcap: Boolean;
begin
  Result := not FileExists(ExpandConstant('{sys}\Npcap\wpcap.dll'));
end;

function NeedsVCRedist: Boolean;
var
  Installed: Cardinal;
begin
  Result := True;
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) then
    Result := (Installed <> 1);
end;
