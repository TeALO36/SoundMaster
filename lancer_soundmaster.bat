@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Premiere installation de SoundMaster...
    call setup_env.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m soundmaster %*
set "EXIT_CODE=%errorlevel%"
endlocal & exit /b %EXIT_CODE%
