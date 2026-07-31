@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Environnement absent. Lancez lancer_soundmaster.bat une premiere fois.
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -e "." >nul
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m soundmaster.core.models status
set "EXIT_CODE=%errorlevel%"
endlocal & exit /b %EXIT_CODE%
