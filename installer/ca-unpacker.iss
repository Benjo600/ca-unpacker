#define AppName "CA Unpacker"
#define AppVersion "0.10.0"
#define AppPublisher "CA Unpacker"
#define AppExeName "CAUnpacker.exe"

[Setup]
AppId={{8F3C2E11-9B4A-4D6E-A1C8-CA00UNPACK01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\CA Unpacker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=CAUnpacker-Setup
; Engine + UI + bundled Tesseract live in dist\CAUnpacker (PyInstaller). No Python on PATH.
Compression=lzma
SolidCompression=yes
WizardStyle=modern
InfoAfterFile=FIRST-RUN.txt
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\apps\ui\app-icon.ico
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\CAUnpacker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Open CA Unpacker"; Flags: nowait postinstall skipifsilent
