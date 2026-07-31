@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Environnement Python absent. Installation en cours...
    call setup_env.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -e "."
if errorlevel 1 (
    echo Impossible d'installer le gestionnaire Hugging Face.
    exit /b 1
)

echo.
echo Profils disponibles : qwen3-tts, qwen3-tts-tokenizer, omnivoice
if "%~1"=="" (
    echo Aucun profil indique.
    echo Usage : installer_modeles.bat qwen3-tts
    echo Pour tout telecharger : installer_modeles.bat all
    exit /b 2
)

if /I "%~1"=="all" (
    ".venv\Scripts\python.exe" -m soundmaster.core.models download qwen3-tts qwen3-tts-tokenizer omnivoice
) else (
    ".venv\Scripts\python.exe" -m soundmaster.core.models download %*
)
set "EXIT_CODE=%errorlevel%"
endlocal & exit /b %EXIT_CODE%
