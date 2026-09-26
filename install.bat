@echo off
setlocal
pushd "%~dp0" || exit /b 1
echo Installing Montenegrin STT Review...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install-windows.ps1" %*
set "STT_EXIT=%ERRORLEVEL%"
popd
if not defined STT_NO_PAUSE pause
endlocal & exit /b %STT_EXIT%
