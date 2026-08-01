@echo off
setlocal

cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Premiere installation de SoundMaster...
    call setup_env.bat
    if errorlevel 1 exit /b 1
) else (
    ".venv\Scripts\python.exe" -c "import PyQt6, keyboard, sounddevice, soundmaster" >nul 2>&1
    if errorlevel 1 (
        echo Dependances manquantes ou environnement incomplet. Reparation...
        call setup_env.bat
        if errorlevel 1 exit /b 1
    )
)

".venv\Scripts\python.exe" -m soundmaster %*
set "EXIT_CODE=%errorlevel%"
endlocal & exit /b %EXIT_CODE%
