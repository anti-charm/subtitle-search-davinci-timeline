@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -3 -m subdav
) else (
    python -m subdav
)

if errorlevel 1 (
    echo.
    echo The application exited with an error.
    echo Run: python -m subdav --check
    pause
)
endlocal
