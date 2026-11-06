@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
if "%SETUP_EXIT%"=="0" (echo Setup complete. Open START_DATA_PREPARATION.bat.) else (echo Setup failed. See SETUP_WINDOWS.log.)
pause
exit /b %SETUP_EXIT%
