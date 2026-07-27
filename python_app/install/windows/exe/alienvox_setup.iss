; AlienVox Windows installer (Inno Setup) - base tier by default,
; with an advanced path that exposes optional setup choices.
;
; Packages the PyInstaller onedir build from
; install\.venv-base-build\build\exe\dist\AlienVox\ into a proper Start
; Menu install with an uninstaller. Requires build_exe.bat to have run
; the PyInstaller freeze step first (it does this automatically before
; invoking ISCC on this script).
;
; Everything transient here - the build venv, the PyInstaller dist/work
; folders, and the compiled installer .exe itself - lives under
; install\.venv-base-build\, one folder already covered by .gitignore's
; ".venv-base-build/" rule.
;
; Compile with the Inno Setup Compiler (ISCC.exe) - free, from
; https://jrsoftware.org/isinfo.php. Not bundled with this repo.

#define MyAppName "AlienVox"
#define MyAppPublisher "AlienTech.Software"
#define MyAppURL "https://alientech.software/"
#define MyAppExeName "AlienVox.exe"
; Version is read from version.yaml at build time by build_exe.bat, which
; passes it via /DMyAppVersion=... - falls back to 0.0.0 if compiled directly.
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
; No admin rights required - installs per-user by default, matching the
; app's own philosophy of not touching anything outside its own folder /
; %LOCALAPPDATA%\com.alientech.alienvox.
PrivilegesRequired=lowest
AppMutex=Global\AlienVox_SingleInstance
CloseApplications=force
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
; Desktop shortcut moved to the final options page so it feels like a last-step choice.

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "redist\VC_redist.x64.exe"; DestDir: "{tmp}"; DestName: "VC_redist.x64.exe"; Flags: deleteafterinstall ignoreversion
Source: "{#DistDir}\_internal\install\assets\audio\ml\piper\en_US-lessac-medium.mp3"; DestName: "preview-sample.mp3"; Flags: dontcopy ignoreversion
#include "installer_samples.generated.iss"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Check: ShouldCreateDesktopShortcut

[Run]
Filename: "{tmp}\VC_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Microsoft Visual C++ runtime..."; Flags: waituntilterminated runhidden; Check: ShouldInstallVCRedist
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; user.yaml / stacks.yaml overrides and the app's own logs live next to
; the exe (see src/config.py) - remove them on uninstall so a reinstall
; starts clean. Does NOT touch %LOCALAPPDATA%\com.alientech.alienvox
; (model weight cache) - that survives an uninstall deliberately, so
; reinstalling doesn't force re-downloading anything.
Type: filesandordirs; Name: "{app}\.logs"
Type: filesandordirs; Name: "{app}\.generated"

[Code]
var
  ExistingInstallUninstallString: string;
  ModePage: TWizardPage;
  BasicRadio: TRadioButton;
  AdvancedRadio: TRadioButton;
  AdvancedPage: TWizardPage;
  FinishPage: TWizardPage;
  CatalogList: TNewCheckListBox;
  PackageDesc: TNewStaticText;
  AutoPlayCheck: TCheckBox;
  DesktopShortcutCheck: TCheckBox;
  PlayErrorCode: Integer;
  VCRedistInstalled: Cardinal;
  CatalogSelectionIndex: Integer;
  CatalogKinds: array of Integer;
  CatalogLabels: array of string;
  CatalogSizes: array of string;
  CatalogStackIds: array of string;
  CatalogModelIds: array of string;
  CatalogVoiceIds: array of string;
  CatalogSampleFiles: array of string;

function IsExistingInstallPresent: Boolean;
begin
  Result := False;
  ExistingInstallUninstallString := '';

  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B6C1E9D2-4F3A-4B7E-9B9C-ALIENVOXBASE}_is1', 'UninstallString', ExistingInstallUninstallString) then
    Result := True
  else if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B6C1E9D2-4F3A-4B7E-9B9C-ALIENVOXBASE}_is1', 'UninstallString', ExistingInstallUninstallString) then
    Result := True;
end;

procedure RunExistingUninstaller();
var
  uninstall_exe: string;
  uninstall_args: string;
  result_code: Integer;
  p: Integer;
begin
  uninstall_exe := ExistingInstallUninstallString;
  uninstall_args := '';

  if Copy(uninstall_exe, 1, 1) = '"' then
  begin
    Delete(uninstall_exe, 1, 1);
    p := Pos('"', uninstall_exe);
    if p > 0 then
    begin
      uninstall_args := Trim(Copy(uninstall_exe, p + 1, Length(uninstall_exe)));
      uninstall_exe := Copy(uninstall_exe, 1, p - 1);
    end;
  end
  else
  begin
    p := Pos(' ', uninstall_exe);
    if p > 0 then
    begin
      uninstall_args := Trim(Copy(uninstall_exe, p + 1, Length(uninstall_exe)));
      uninstall_exe := Copy(uninstall_exe, 1, p - 1);
    end;
  end;

  if uninstall_exe = '' then
  begin
    MsgBox('AlienVox appears to be installed, but the uninstaller entry could not be read. Please uninstall it from Windows Settings, then run setup again.', mbError, MB_OK);
    Abort();
  end;

  if not Exec(uninstall_exe, uninstall_args + ' /VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_SHOW, ewWaitUntilTerminated, result_code) then
  begin
    MsgBox('AlienVox is already installed, but the uninstaller could not be started. Please uninstall it manually, then rerun setup.', mbError, MB_OK);
    Abort();
  end;

  MsgBox('AlienVox has been uninstalled. Please run the installer again to install the new version.', mbInformation, MB_OK);
  Abort();
end;

procedure AddCatalogItem(Kind: Integer; LabelText, SizeText, StackId, ModelId, VoiceId, SampleFile: string);
var
  i: Integer;
begin
  i := GetArrayLength(CatalogKinds);
  SetArrayLength(CatalogKinds, i + 1);
  SetArrayLength(CatalogLabels, i + 1);
  SetArrayLength(CatalogSizes, i + 1);
  SetArrayLength(CatalogStackIds, i + 1);
  SetArrayLength(CatalogModelIds, i + 1);
  SetArrayLength(CatalogVoiceIds, i + 1);
  SetArrayLength(CatalogSampleFiles, i + 1);
  CatalogKinds[i] := Kind;
  CatalogLabels[i] := LabelText;
  CatalogSizes[i] := SizeText;
  CatalogStackIds[i] := StackId;
  CatalogModelIds[i] := ModelId;
  CatalogVoiceIds[i] := VoiceId;
  CatalogSampleFiles[i] := SampleFile;
end;

procedure InitCatalog;
begin
  SetArrayLength(CatalogKinds, 0);
  SetArrayLength(CatalogLabels, 0);
  SetArrayLength(CatalogSizes, 0);
  SetArrayLength(CatalogStackIds, 0);
  SetArrayLength(CatalogModelIds, 0);
  SetArrayLength(CatalogVoiceIds, 0);
  SetArrayLength(CatalogSampleFiles, 0);
#include "installer_catalog.generated.iss"
end;

function GetSamplePath: string;
begin
  Result := ExpandConstant('{tmp}\preview-sample.mp3');
end;

function MciSendString(Command: string; ReturnString: string; ReturnLength: Integer; CallbackWnd: Integer): Longint;
  external 'mciSendStringW@winmm.dll stdcall';

function GetCatalogSampleIndex: Integer;
var
  i: Integer;
begin
  Result := CatalogSelectionIndex;
  if (Result < 0) or (Result >= GetArrayLength(CatalogKinds)) then
  begin
    Result := -1;
    Exit;
  end;

  if CatalogKinds[Result] = 2 then
    Exit;

  for i := Result + 1 to GetArrayLength(CatalogKinds) - 1 do
  begin
    if CatalogKinds[i] = 1 then
      Break;
    if CatalogKinds[i] = 2 then
    begin
      Result := i;
      Exit;
    end;
  end;

  Result := -1;
end;

procedure PlaySampleButtonClick(Sender: TObject);
var
  sample_index: Integer;
  sample_path: string;
begin
  sample_index := GetCatalogSampleIndex();
  if sample_index < 0 then
  begin
    MsgBox('Select a voice sample first.', mbInformation, MB_OK);
    Exit;
  end;

  MciSendString('stop AlienVoxPreview', '', 0, 0);
  MciSendString('close AlienVoxPreview', '', 0, 0);
  sample_path := ExpandConstant('{tmp}\') + CatalogSampleFiles[sample_index];
  ExtractTemporaryFile(CatalogSampleFiles[sample_index]);
  if not FileExists(sample_path) then
    MsgBox('Bundled sample not found in the installer payload.', mbError, MB_OK)
  else
  begin
    MciSendString('close AlienVoxPreview', '', 0, 0);
    MciSendString('open "' + sample_path + '" type mpegvideo alias AlienVoxPreview', '', 0, 0);
    MciSendString('play AlienVoxPreview from 0', '', 0, 0);
  end;
end;

procedure UpdateAdvancedDescription;
begin
  if (CatalogSelectionIndex < 0) or (CatalogSelectionIndex >= GetArrayLength(CatalogLabels)) then
    PackageDesc.Caption := 'Select a package to see its description.'
  else
    case CatalogKinds[CatalogSelectionIndex] of
      0: PackageDesc.Caption := CatalogLabels[CatalogSelectionIndex] + ' is the stack header.';
      1: PackageDesc.Caption := CatalogLabels[CatalogSelectionIndex] + ' is a model bundle for the selected stack.';
      2:
        begin
          PackageDesc.Caption := CatalogLabels[CatalogSelectionIndex] + ' is a voice sample. ' +
            'Use it to preview how this voice sounds before installing the full model.';
        end;
    else
      PackageDesc.Caption := 'Select a package to see its description.';
    end;
end;

procedure PackageOptionClick(Sender: TObject);
var
  i: Integer;
  selected_kind: Integer;
begin
  if (CatalogList.ItemIndex < 0) or (CatalogList.ItemIndex >= GetArrayLength(CatalogKinds)) then
  begin
    UpdateAdvancedDescription();
    Exit;
  end;

  selected_kind := CatalogKinds[CatalogList.ItemIndex];
  if selected_kind = 1 then
  begin
    for i := CatalogList.ItemIndex + 1 to GetArrayLength(CatalogKinds) - 1 do
    begin
      if CatalogKinds[i] = 1 then
        Break;
      if CatalogKinds[i] = 2 then
        CatalogList.Checked[i] := CatalogList.Checked[CatalogList.ItemIndex];
    end;
  end;

  UpdateAdvancedDescription();
  if (selected_kind = 2) and Assigned(AutoPlayCheck) and AutoPlayCheck.Checked and (GetCatalogSampleIndex() >= 0) then
    PlaySampleButtonClick(Sender);
end;

procedure CatalogListClick(Sender: TObject);
begin
  if CatalogList.ItemIndex >= 0 then
    CatalogSelectionIndex := CatalogList.ItemIndex;
  UpdateAdvancedDescription();
  if (CatalogSelectionIndex >= 0) and (CatalogSelectionIndex < GetArrayLength(CatalogKinds)) and
     (CatalogKinds[CatalogSelectionIndex] = 2) and Assigned(AutoPlayCheck) and AutoPlayCheck.Checked and
     (GetCatalogSampleIndex() >= 0) then
    PlaySampleButtonClick(Sender);
end;

procedure InitializeWizard;
var
  i: Integer;
  display_text: string;
begin
  ModePage := CreateCustomPage(wpSelectDir, 'Installation mode', 'Choose how AlienVox should be installed');

  BasicRadio := TRadioButton.Create(ModePage.Surface);
  BasicRadio.Parent := ModePage.Surface;
  BasicRadio.Left := ScaleX(0);
  BasicRadio.Top := ScaleY(32);
  BasicRadio.Width := ScaleX(400);
  BasicRadio.Caption := 'Basic';
  BasicRadio.Checked := True;

  AdvancedRadio := TRadioButton.Create(ModePage.Surface);
  AdvancedRadio.Parent := ModePage.Surface;
  AdvancedRadio.Left := ScaleX(0);
  AdvancedRadio.Top := BasicRadio.Top + ScaleY(20);
  AdvancedRadio.Width := ScaleX(400);
  AdvancedRadio.Caption := 'Advanced';

  AdvancedPage := CreateCustomPage(wpSelectTasks, 'Custom install', 'Choose optional packages and preview samples');
  InitCatalog();

  CatalogList := TNewCheckListBox.Create(AdvancedPage.Surface);
  CatalogList.Parent := AdvancedPage.Surface;
  CatalogList.Left := ScaleX(0);
  CatalogList.Top := ScaleY(8);
  CatalogList.Width := ScaleX(410);
  CatalogList.Height := ScaleY(190);
  CatalogList.OnClick := @CatalogListClick;
  CatalogList.OnClickCheck := @PackageOptionClick;

  for i := 0 to GetArrayLength(CatalogLabels) - 1 do
  begin
    display_text := CatalogLabels[i];
    if CatalogSizes[i] <> '' then
      display_text := display_text + '   ' + CatalogSizes[i];
    CatalogList.AddCheckBox(display_text, '', 0, CatalogKinds[i] <> 0, True, False, False, nil);
  end;
  CatalogSelectionIndex := 0;
  if GetArrayLength(CatalogLabels) > 0 then
    CatalogList.ItemIndex := 0;

  AutoPlayCheck := TCheckBox.Create(AdvancedPage.Surface);
  AutoPlayCheck.Parent := AdvancedPage.Surface;
  AutoPlayCheck.Left := ScaleX(430);
  AutoPlayCheck.Top := ScaleY(28);
  AutoPlayCheck.Width := ScaleX(160);
  AutoPlayCheck.Caption := 'Auto-play sample on selection';
  AutoPlayCheck.Checked := False;

  PackageDesc := TNewStaticText.Create(AdvancedPage.Surface);
  PackageDesc.Parent := AdvancedPage.Surface;
  PackageDesc.Left := ScaleX(0);
  PackageDesc.Top := ScaleY(210);
  PackageDesc.Width := ScaleX(530);
  PackageDesc.Height := ScaleY(48);
  PackageDesc.WordWrap := True;
  PackageDesc.Caption := 'Select a package to see its description.';
  UpdateAdvancedDescription();

  FinishPage := CreateCustomPage(wpReady, 'Final options', 'One last choice before installation');
  DesktopShortcutCheck := TCheckBox.Create(FinishPage.Surface);
  DesktopShortcutCheck.Parent := FinishPage.Surface;
  DesktopShortcutCheck.Left := ScaleX(0);
  DesktopShortcutCheck.Top := ScaleY(16);
  DesktopShortcutCheck.Width := ScaleX(300);
  DesktopShortcutCheck.Caption := 'Create a desktop shortcut';
  DesktopShortcutCheck.Checked := False;
end;

function UseAdvancedInstall: Boolean;
begin
  Result := Assigned(AdvancedRadio) and AdvancedRadio.Checked;
end;

function ShouldCreateDesktopShortcut: Boolean;
begin
  Result := Assigned(DesktopShortcutCheck) and DesktopShortcutCheck.Checked;
end;

function ShouldInstallVCRedist: Boolean;
begin
  Result := True;
  if RegKeyExists(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') then
  begin
    if RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', VCRedistInstalled) then
      Result := VCRedistInstalled <> 1;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if Assigned(AdvancedPage) and (PageID = AdvancedPage.ID) then
    Result := not UseAdvancedInstall();
end;

function InitializeSetup: Boolean;
var
  response: Integer;
begin
  Result := True;
  if IsExistingInstallPresent() then
  begin
    response := MsgBox(
      'AlienVox is already installed on this machine.'#13#10#13#10 +
      'Choose Yes to run the existing uninstaller first.'#13#10 +
      'Choose No to continue with a repair/reinstall.'#13#10 +
      'Choose Cancel to stop setup.',
      mbConfirmation, MB_YESNOCANCEL);

    if response = IDYES then
      RunExistingUninstaller()
    else if response = IDCANCEL then
      Result := False;
  end;
end;
