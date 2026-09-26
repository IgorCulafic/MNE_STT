@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" "tools\launch.py" %*
set "STT_EXIT=%ERRORLEVEL%"
goto done
:missing
echo Run install.bat first. Then double-click run.bat again.
set "STT_EXIT=1"
:done
popd
if not "%STT_EXIT%"=="0" if not defined STT_NO_PAUSE pause
endlocal & exit /b %STT_EXIT%
