@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup_env.bat first.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\packaging\build_windows.ps1" -PythonExecutable "%~dp0.venv\Scripts\python.exe" %*
set "EXIT_CODE=%errorlevel%"
endlocal & exit /b %EXIT_CODE%
