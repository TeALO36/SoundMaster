@echo off
setlocal

cd /d "%~dp0"
set "VENV_DIR=%~dp0.venv"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 goto :find_py_launcher

python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_failed
set "PYTHON_CMD=python"
goto :create_venv

:find_py_launcher
rem Prefer Python 3.11 for the broadest compatibility, then newer supported versions.
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.11"
if defined PYTHON_CMD goto :create_venv
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if defined PYTHON_CMD goto :create_venv
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.13"
if defined PYTHON_CMD goto :create_venv
py -3.14 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.14"
if defined PYTHON_CMD goto :create_venv

:venv_failed
echo Failed to find a supported Python interpreter. Install Python 3.11, 3.12, 3.13, or 3.14 first.
exit /b 1

:create_venv
if exist "%VENV_DIR%\Scripts\python.exe" goto :validate_existing_venv
%PYTHON_CMD% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo Failed to create the virtual environment.
    exit /b 1
)
goto :venv_ready

:validate_existing_venv
"%VENV_DIR%\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Existing .venv uses an unsupported Python version.
    echo Delete .venv and run setup_env.bat again to recreate it with Python 3.11-3.14.
    exit /b 1
)

:venv_ready
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

python -m pip install -e ".[dev,build]"
if errorlevel 1 (
    echo Failed to install SoundMaster dependencies.
    exit /b 1
)

echo.
echo SoundMaster environment is ready.
echo Run lancer_soundmaster.bat to launch the application.
echo Run telecharger_modeles.bat to download public Hugging Face models.

endlocal
