@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\check_portable.py" %*
) else (
  echo Run SETUP_WINDOWS.bat first. The check uses this folder's Python environment.
  popd
  pause
  exit /b 1
)
set "CHECK_EXIT=%ERRORLEVEL%"
popd
pause
exit /b %CHECK_EXIT%
