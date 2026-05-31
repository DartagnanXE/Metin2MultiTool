; ===================================================================
;  Metin2 Fishing Bot - Inno-Setup-Skript
;  Verpackt den PyInstaller-onedir-Output (dist\Metin2FishBot\) zu
;  EINEM signierbaren Setup.exe -> fuer Laien weiterhin ein Doppelklick.
;
;  Bauen:  ISCC.exe installer.iss        (oder via build.bat automatisch)
;  Voraussetzung: vorher `pyinstaller ... Metin2FishBot.spec` ausfuehren,
;  damit dist\Metin2FishBot\Metin2FishBot.exe existiert.
;
;  WARUM EIN INSTALLER GEGEN FALSE-POSITIVES HILFT:
;    - Inno-Setup-Stubs sind weit verbreitet & gut reputiert (weniger FP als
;      eine nackte, frisch gebaute EXE).
;    - Installer ist signierbar (SignTool) -> mit Zertifikat verschwinden die
;      meisten Heuristik-Warnungen. Siehe [Setup] SignTool unten.
; ===================================================================

#define AppName "Metin2 Fishing Bot"
#define AppVersion "1.0.1"
#define AppPublisher "Musketier Software"
#define AppExeName "Metin2FishBot.exe"
; Quelle: der gesamte onedir-Ordner aus dem PyInstaller-Build.
#define DistDir "dist\Metin2FishBot"

[Setup]
; Stabile GUID (nicht aendern - identifiziert das Produkt fuer Updates/Deinstall).
AppId={{B6F3A7C2-4E1D-4A9B-9C8E-2D7F1A0B5E64}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Metin2FishBot
DefaultGroupName=Metin2 Fishing Bot
; Standardinstallation pro Maschine -> braucht Admin (passt: Bot laeuft als Admin).
PrivilegesRequired=admin
; Architektur: 64-bit Build (x64compatible deckt x64 + ARM64-Emulation ab).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=Metin2FishBot_Setup_{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Lizenz-/Haftungshinweis im Assistenten anzeigen (Nutzer muss zustimmen).
LicenseFile=LICENSE.txt
; Windows 10 oder neuer.
MinVersion=10.0
; Setup-/App-Icon, falls 'musketier.ico' neben dieser .iss liegt.
#if FileExists("musketier.ico")
SetupIconFile=musketier.ico
#endif
; Versions-Metadaten der Setup.exe selbst (analog zur PE-Ressource der App).
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
; Deinstaller-Icon = das App-Icon.
UninstallDisplayIcon={app}\{#AppExeName}

; --- CODE-SIGNING (optional, dringend empfohlen gegen False-Positives) -------
; Wenn ein Code-Signing-Zertifikat vorhanden ist, in der Inno-Setup-IDE unter
;   Tools > Configure Sign Tools...
; einen Sign-Tool-Eintrag namens "signtool" anlegen, z. B.:
;   signtool=$qC:\Path\signtool.exe$q sign /fd sha256 /a /tr http://timestamp.digicert.com /td sha256 $f
; Dann die folgenden zwei Zeilen entkommentieren -> Setup UND die App-EXE
; werden beim Build automatisch signiert:
;   SignTool=signtool
;   SignedUninstaller=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Der KOMPLETTE onedir-Output rekursiv (EXE + alle DLLs + images\ + JSON/TXT).
; {#DistDir}\* deckt auch die eingebetteten Assets ab.
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Nach der Installation optional direkt starten - als Admin (runascurrentuser,
; da das Setup bereits elevated laeuft). Spiel muss in 800x600 laufen.
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallDelete]
; Zur Laufzeit erzeugte Dateien (Strategie-Cache / Einstellungen / Log) sauber
; mitentfernen, damit nach der Deinstallation nichts zurueckbleibt.
Type: files; Name: "{app}\trained_V.npy"
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\puzzle_debug.log"
Type: filesandordirs; Name: "{app}\__pycache__"
