@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Preparation de l'environnement SoundMaster...
    call setup_env.bat
    if errorlevel 1 goto :failed
)

where nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo Aucun outil NVIDIA detecte. Installez le pilote NVIDIA avant de continuer.
    goto :failed
)

nvidia-smi --query-gpu=name --format=csv,noheader
if errorlevel 1 (
    echo Aucun GPU NVIDIA utilisable detecte.
    goto :failed
)

echo Installation de PyTorch CUDA 12.6 pour NVIDIA...
".venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps ^
    torch==2.11.0+cu126 torchaudio==2.11.0+cu126 ^
    --index-url https://download.pytorch.org/whl/cu126
if errorlevel 1 goto :failed

echo Installation du runtime vocal Qwen3-TTS et de la transcription locale...
".venv\Scripts\python.exe" -m pip install qwen-tts soundfile faster-whisper
if errorlevel 1 goto :failed


echo.
echo Verification CUDA...
".venv\Scripts\python.exe" -c "import torch, torchaudio; ok=torch.cuda.is_available() and torch.version.cuda == '12.6' and '+cu126' in torch.__version__ and '+cu126' in torchaudio.__version__; print('PyTorch:', torch.__version__); print('TorchAudio:', torchaudio.__version__); print('CUDA:', torch.version.cuda); print('GPU disponible:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'aucun'); print('BF16:', torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False); raise SystemExit(0 if ok else 1)"
if errorlevel 1 goto :failed

echo.
echo Runtime GPU SoundMaster pret.
echo Lancez lancer_soundmaster.bat puis ouvrez Clonage de voix.
endlocal & exit /b 0

:failed
echo.
echo Echec de l'installation GPU. Verifiez la connexion, le pilote NVIDIA et l'espace disque.
endlocal & exit /b 1
