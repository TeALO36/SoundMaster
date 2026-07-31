# Changelog

## 0.2.0 — 2026-08-01

### Added

- French PyQt6 soundboard shell with dashboard, voice cloning, Myinstants explorer, global shortcuts, settings, and system tray support.
- Local Myinstants search, previews, rights confirmation, cached downloads, favorites, and multi-download progress.
- Local Qwen3-TTS and OmniVoice integration points with optional automatic Faster-Whisper transcription.
- NVIDIA CUDA setup script with aligned PyTorch/TorchAudio wheels and BF16/FP16 fallback handling.
- GPU/TTS diagnostics in Settings, including CUDA, VRAM, BF16, runtime, and model availability.
- Windows packaging workflow for an Inno Setup installer and portable ZIP, plus automatic GitHub Releases.
- Compliance settings, publisher/legal document references, privacy defaults, third-party notices, and release checks.
- Regression coverage for UI startup, Myinstants flows, library persistence, GPU diagnostics, voice workers, and transcript-free Qwen generation.

### Validation

- 33 automated tests passed.
- Ruff and Python compilation passed.
- Offscreen UI startup, navigation, and shutdown passed.
- Live Myinstants search and MP3 cache download passed.
- Qwen3-TTS GPU generation passed on an NVIDIA RTX 4050 Laptop GPU with CUDA 12.6 and BF16.

### Notes

- Release artifacts are unsigned; configure Authenticode signing before commercial distribution.
- Qwen3-TTS, OmniVoice, Faster-Whisper, Myinstants content, and user-provided audio remain subject to their own licenses, rights, and terms.
- SoX and `flash-attn` are optional performance/runtime improvements and are not required by the validated Qwen generation path.
