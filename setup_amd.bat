@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Preparation de l'environnement SoundMaster...
    call setup_env.bat
    if errorlevel 1 goto :failed
)

echo Installation de PyTorch ROCm 6.4 pour GPU AMD...
".venv\Scripts\python.exe" -m pip install --force-reinstall --no-deps ^
    torch==2.9.0+rocm6.4 torchaudio==2.9.0+rocm6.4 ^
    --index-url https://download.pytorch.org/whl/rocm6.4
if errorlevel 1 goto :failed

echo Installation du runtime vocal Qwen3-TTS et de la transcription locale...
".venv\Scripts\python.exe" -m pip install qwen-tts soundfile faster-whisper
if errorlevel 1 goto :failed

echo.
echo Verification ROCm...
".venv\Scripts\python.exe" -c "import torch, torchaudio; ok=torch.cuda.is_available() and bool(getattr(torch.version, 'hip', None)); print('PyTorch:', torch.__version__); print('TorchAudio:', torchaudio.__version__); print('ROCm:', getattr(torch.version, 'hip', 'inconnue')); print('GPU disponible:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'aucun'); print('BF16:', torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False); raise SystemExit(0 if ok else 1)"
if errorlevel 1 goto :failed

echo.
echo Runtime GPU AMD SoundMaster pret.
echo Lancez lancer_soundmaster.bat puis ouvrez Clonage de voix.
endlocal & exit /b 0

:failed
echo.
echo Echec de l'installation GPU AMD. Verifiez la connexion, le pilote AMD (Adrenalin) et l'espace disque.
endlocal & exit /b 1
