@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "STT_NO_PAUSE=1"
call install.bat
set "STT_EXIT=%ERRORLEVEL%"
if not "%STT_EXIT%"=="0" goto done
call download-models.bat
set "STT_EXIT=%ERRORLEVEL%"
:done
popd
if "%STT_EXIT%"=="0" echo Setup complete. Double-click run.bat to start.
pause
endlocal & exit /b %STT_EXIT%
