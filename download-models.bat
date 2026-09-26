@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" "tools\download_models.py" %*
set "STT_EXIT=%ERRORLEVEL%"
goto done
:missing
echo Run install.bat first to install Python and the app dependencies.
set "STT_EXIT=1"
:done
popd
if not defined STT_NO_PAUSE pause
endlocal & exit /b %STT_EXIT%
