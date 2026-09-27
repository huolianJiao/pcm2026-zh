@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launcher.ps1" -Mode Recover
set "PCM26_RESULT=%ERRORLEVEL%"
pause
exit /b %PCM26_RESULT%
