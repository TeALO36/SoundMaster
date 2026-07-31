@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Premiere installation de SoundMaster...
    call setup_env.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -e "."
if errorlevel 1 (
    echo Impossible d'installer le telechargeur Hugging Face.
    exit /b 1
)

echo.
echo Les modeles sont volumineux et peuvent occuper plusieurs dizaines de Go.
echo Telechargement public sans cle API ni service d'inference distant.
echo.
if "%~1"=="" (
    echo Profils : qwen3-tts, qwen3-tts-tokenizer, omnivoice
    echo Usage cible : telecharger_modeles.bat qwen3-tts
    echo Pour tout telecharger, utilisez : telecharger_modeles.bat all
    set /p "MODEL_CHOICE=Profil a telecharger [qwen3-tts]: "
    if not defined MODEL_CHOICE set "MODEL_CHOICE=qwen3-tts"
) else (
    set "MODEL_CHOICE=%~1"
)

if /I "%MODEL_CHOICE%"=="all" (
    ".venv\Scripts\python.exe" -m soundmaster.core.models download qwen3-tts qwen3-tts-tokenizer omnivoice
) else (
    ".venv\Scripts\python.exe" -m soundmaster.core.models download "%MODEL_CHOICE%"
)
set "EXIT_CODE=%errorlevel%"

echo.
if "%EXIT_CODE%"=="0" echo Modele(s) disponibles localement.
if not "%EXIT_CODE%"=="0" echo Le telechargement a echoue. Verifiez votre connexion et l'espace disque.
endlocal & exit /b %EXIT_CODE%
