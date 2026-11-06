@echo off
setlocal EnableExtensions DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_data_preparation.ps1" %*
echo.
echo See DATA_PREPARATION_STARTUP.log in this folder for startup diagnostics.
pause
