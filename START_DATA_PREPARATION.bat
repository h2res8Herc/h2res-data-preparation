@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_data_preparation.ps1" %*
set "PREPARATION_EXIT=%ERRORLEVEL%"
if "%PREPARATION_EXIT%"=="0" exit /b 0
echo.
echo Data preparation could not start. See DATA_PREPARATION_STARTUP.log in this folder.
pause
exit /b %PREPARATION_EXIT%
