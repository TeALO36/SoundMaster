@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Premiere installation de SoundMaster...
    call setup_env.bat
    if errorlevel 1 goto :failed
) else (
    ".venv\Scripts\python.exe" -c "import PyQt6, soundmaster" >nul 2>&1
    if errorlevel 1 (
        echo Dependances manquantes ou environnement incomplet. Reparation...
        call setup_env.bat
        if errorlevel 1 goto :failed
    )
)

".venv\Scripts\python.exe" -m soundmaster %*
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" goto :failed
endlocal & exit /b 0

:failed
echo.
echo SoundMaster n'a pas pu demarrer. Consultez le message ci-dessus.
pause
exit /b 1
