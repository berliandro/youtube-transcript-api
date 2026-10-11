@echo off
rem Double-click launcher for get_transcript.py
rem Runs the app in this folder and keeps errors visible.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py get_transcript.py %*
    goto :done
)
where python >nul 2>nul
if %errorlevel%==0 (
    python get_transcript.py %*
    goto :done
)
where python3 >nul 2>nul
if %errorlevel%==0 (
    python3 get_transcript.py %*
    goto :done
)
echo Could not find Python. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
exit /b 1
:done
rem The Python app already pauses at the end when double-clicked.
rem This extra pause only matters if the app crashed before reaching its own pause.
if errorlevel 1 pause
