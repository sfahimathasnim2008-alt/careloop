@echo off
cd /d "%~dp0"
set PY=
where python >nul 2>nul
if %errorlevel%==0 set PY=python
if "%PY%"=="" (
  where py >nul 2>nul
  if %errorlevel%==0 set PY=py
)
if "%PY%"=="" goto nopython
echo Installing Flask (first time only)...
%PY% -m pip install -r requirements.txt
echo.
%PY% app.py
pause
exit /b
:nopython
echo Python was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then double-click run.bat again.
pause
