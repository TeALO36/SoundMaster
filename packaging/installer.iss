#ifndef MyAppVersion
  #define MyAppVersion "0.6.0"
#endif

#define MyAppName "SoundMaster"
#define MyAppPublisher "SoundMaster"
#define MyAppExeName "SoundMaster.exe"
#ifndef MyAppPublisherURL
  #define MyAppPublisherURL "https://github.com/TeALO36/SoundMaster"
#endif

[Setup]
AppId={{A6D3AB0F-2C26-4B84-B6B4-5C8CF2F118C4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppPublisherURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=SoundMaster-v{#MyAppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\SoundMaster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis supplémentaires:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer SoundMaster"; Flags: nowait postinstall skipifsilent
