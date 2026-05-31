@echo off
REM ===================================================================
REM  Metin2 FishBot - DEBUG-Modus (Quellcode, mit sichtbarer Konsole)
REM  Nutze dies zur Fehlersuche am Puzzle: du siehst JEDE State-
REM  Transition und die erkannten Stein-Farben LIVE in der Konsole.
REM  Zusaetzlich wird puzzle_debug.log geschrieben.
REM  (Die gebaute EXE laeuft bewusst OHNE Konsole - daher dieser Modus.)
REM ===================================================================
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo === Metin2 FishBot: DEBUG (Quellcode + Konsole) ===
echo Schliesse dieses Fenster zum Beenden.
echo.
%PY% hack.py

echo.
echo (Bot beendet.) Logdatei: puzzle_debug.log
pause
