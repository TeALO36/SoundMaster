# SoundMaster

SoundMaster is a local-first Windows soundboard for gamers. It will provide offline sound playback, dual audio outputs, local Qwen3-TTS voice generation, Myinstants caching, favorites, and global keybinds.

## Current status

Step 1 is complete: the repository has a Python package layout, Windows virtual-environment bootstrap scripts, application data paths, structured logging, and a minimal PyQt6 entry point. Audio routing, the four production UI sections, Myinstants integration, TTS inference, and global hotkeys are intentionally deferred to the next implementation steps.

## Requirements

- Windows 10 or newer
- Python 3.11, 3.12, 3.13, or 3.14
- NVIDIA drivers and CUDA-compatible PyTorch will be added with the local TTS integration
- A headset and virtual audio cable for the later routing step
- Inno Setup 6 only when building the installer locally

## Setup (Windows)

From the repository root, double-click `setup_env.bat`, or run it from Command Prompt:

```bat
setup_env.bat
```

The script creates `.venv`, upgrades pip, and installs the package in editable mode with development tools. It uses the Windows `py` launcher when available (otherwise `python`), so the selected interpreter must satisfy the supported Python range above.

## Launch

```bat
run_soundmaster.bat
```

Or, after activating the environment:

```bat
.venv\\Scripts\\activate
python -m soundmaster
```

The current bootstrap window is deliberately small and reports that audio routing is not enabled yet. Its **Paramètres** button opens the French compliance center. This center is a technical release checklist, not legal advice or a legal certification.

For a quick Windows start, double-click [`lancer_soundmaster.bat`](lancer_soundmaster.bat). To download the public Hugging Face snapshots without an inference API key, double-click [`telecharger_modeles.bat`](telecharger_modeles.bat), choose a profile, then use [`statut_modeles.bat`](statut_modeles.bat) to inspect local availability. The current model manager downloads files only; wiring model inference into the Voice Cloning screen remains a separate implementation step.

Before commercial distribution, the publisher must provide and have counsel review the applicable legal documents, confirm rights for every bundled/downloaded audio asset, verify the exact Qwen model license and NOTICE, and decide the markets and sales process. The Myinstants terms currently describe personal, non-commercial access; do not commercialize downloaded Myinstants sounds without written rights clearance.

## Local data

Runtime files are kept outside the repository by default:

`%LOCALAPPDATA%\\SoundMaster\\`

The application will use these locations in later steps:

- `soundmaster.db` — favorites, history, cloned voice metadata, and keybinds
- `legal_profile.json` — publisher identity, legal-document references, privacy defaults, and release checklist
- `audio-cache\\` — favorited Myinstants and generated audio files
- `voice-samples\\` — user-provided voice samples
- `logs\\soundmaster.log` — rotating application logs
- `models\\` — public Hugging Face model snapshots (can be redirected with `SOUNDMASTER_MODEL_DIR`)

Set `SOUNDMASTER_DATA_DIR` to override the data directory, for example when developing against a disposable local profile.

## Development checks

```bat
.venv\\Scripts\\python -m compileall src
.venv\\Scripts\\ruff check src
.venv\\Scripts\\pytest
```

## Local voice models (no API)

The model downloader uses the public Hugging Face Hub via `huggingface_hub.snapshot_download`; it does not call a hosted inference service and does not require an API key for the public repositories below:

| Profile | Repository | Role |
| --- | --- | --- |
| `qwen3-tts` | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | Qwen3-TTS voice cloning/generation base model |
| `qwen3-tts-tokenizer` | `Qwen/Qwen3-TTS-Tokenizer-12Hz` | Qwen3-TTS audio tokenizer |
| `omnivoice` | `k2-fsa/OmniVoice` | Alternative multilingual zero-shot voice model |

Use a separate high-capacity disk if needed:

```bat
set SOUNDMASTER_MODEL_DIR=D:\\SoundMasterModels
telecharger_modeles.bat qwen3-tts
```

The snapshots are large and downloads can take a long time. Check the exact model card, license, revision, storage, and GPU requirements before redistribution. A 24 GB NVIDIA GPU is a strong target for the 1.7B Qwen model, but actual VRAM use depends on dtype, runtime, tokenizer, and generation settings. Downloading weights does not grant rights to clone a person’s voice or redistribute model files.

## Windows distribution

The project now includes reproducible packaging for Windows:

- a per-user `SoundMaster-v<version>-Setup.exe` installer built with Inno Setup;
- a `SoundMaster-v<version>-Portable.zip` package built with PyInstaller `onedir`;
- automatic GitHub Releases for tags matching `vMAJOR.MINOR.PATCH`.

Build locally with PowerShell:

```powershell
python -m pip install ".[dev,build]"
.\packaging\build_windows.ps1 -Version 0.1.0
```

See [`packaging/README.md`](packaging/README.md) for release tags, portable storage, signing, and CI details. The release workflow creates unsigned artifacts; code signing must be configured separately for a polished commercial Windows release.

## Planned implementation order

1. Project and environment foundation (current)
2. French PyQt6 shell, sidebar, tray behavior, and settings page
3. Audio routing engine with headset preview and virtual-cable output
4. Myinstants search, download, and offline cache
5. Local Qwen3-TTS voice generation and history
6. Global hotkeys and dashboard wiring

## Commercialization warning

The application cannot make the publisher legally compliant by itself. The release gate in Settings only prevents an accidental claim of readiness when required information or checks are missing. It does not replace legal advice, a GDPR/RGPD analysis, consumer-law review, accessibility work, security review, tax/VAT setup, software-asset license audit, or rights clearances.

The compliance center is designed around official sources including [CNIL AI/GDPR guidance](https://www.cnil.fr/en/ai-system-development-cnils-recommendations-to-comply-gdpr), the [EU AI Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj), [Myinstants Terms of Use](https://www.myinstants.com/en/terms_of_use.html), and the [Qwen3-TTS license](https://github.com/QwenLM/Qwen3-TTS/blob/main/LICENSE). Verify the current versions before release.
