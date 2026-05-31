@echo off
REM ===================================================================
REM  Metin2 Fishing Bot - Build (Doppelklick genuegt)
REM
REM  1) Abhaengigkeiten installieren (gepinnte requirements.txt)
REM  2) PyInstaller-Build -> dist\Metin2FishBot\  (--onedir, upx=False,
REM     PE-Metadaten; siehe Metin2FishBot.spec)
REM  3) Inno-Setup-Installer bauen -> installer_output\Metin2FishBot_Setup_*.exe
REM     (uebersprungen, falls Inno Setup / ISCC nicht gefunden wird)
REM
REM  Ergebnis fuer Laien: EIN Setup.exe zum Doppelklick. Fuer Entwickler:
REM  der lauffaehige onedir-Ordner unter dist\Metin2FishBot\.
REM ===================================================================
cd /d "%~dp0"
echo === Metin2 Fishing Bot: Build (onedir + Installer) ===

REM Python finden (py-Launcher bevorzugt, sonst python)
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo [1/4] Abhaengigkeiten installieren (robust ueber Python 3.11-3.13)
%PY% -m pip install --upgrade pip >nul 2>nul
%PY% -m pip install --prefer-binary -r requirements.txt || goto :err

echo [2/4] Alte Build-Artefakte aufraeumen
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/4] PyInstaller-Build (--onedir, upx=False, PE-Metadaten)
%PY% -m PyInstaller --clean --noconfirm Metin2FishBot.spec || goto :err

if not exist "dist\Metin2FishBot\Metin2FishBot.exe" (
    echo *** FEHLER: dist\Metin2FishBot\Metin2FishBot.exe wurde nicht erzeugt.
    goto :err
)

echo [4/4] Inno-Setup-Installer bauen (optional)
REM ISCC.exe suchen: PATH, dann uebliche Programme-Pfade.
set "ISCC="
where ISCC >nul 2>nul && set "ISCC=ISCC"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo     [Hinweis] Inno Setup ^(ISCC.exe^) nicht gefunden - Installer uebersprungen.
    echo     Inno Setup 6 installieren: https://jrsoftware.org/isdl.php
    echo     Der lauffaehige Ordner liegt bereits unter:  dist\Metin2FishBot\
    goto :done_noinstaller
)

"%ISCC%" installer.iss || goto :err
echo.
echo FERTIG. Setup liegt in:  installer_output\
echo Verteile dieses Setup.exe an die Nutzer (Doppelklick-Installation).
goto :end

:done_noinstaller
echo.
echo FERTIG (ohne Installer). Starte/teste direkt:
echo     dist\Metin2FishBot\Metin2FishBot.exe
echo (Als Admin starten. Spiel in 800x600, nicht Vollbild.)
echo Diagnose landet in:  puzzle_debug.log  (neben der EXE)

:end
echo.
pause
exit /b 0

:err
echo.
echo *** FEHLER beim Build. Bitte die Ausgabe oben pruefen. ***
echo Haeufige Ursache: Python 3.11-3.13 (64-bit) noetig. Bei Wheel-/Netzwerk-
echo Problemen:  py -m pip install --upgrade pip   und erneut starten.
pause
exit /b 1
