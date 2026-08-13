# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the SoundMaster Windows distribution."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

sounddevice_datas, sounddevice_binaries, sounddevice_hiddenimports = collect_all("sounddevice")
# soundfile decodes WAV/MP3/OGG/FLAC for the zero-latency playback path. It is
# collected explicitly (not just via PyInstaller's hook) so the packaged app can
# never silently lose it and fall back to the slow QMediaPlayer path.
soundfile_datas, soundfile_binaries, soundfile_hiddenimports = collect_all("soundfile")
# pocket_tts is the default voice engine: without it, is_engine_runtime_installed()
# returns False in the packaged app, the generation fallback switches to another
# engine and the user is asked to download a model they never chose. Collect it
# explicitly (package data like the language configs included) exactly like
# soundfile so a future build can never silently drop the default engine. A
# build environment without the `pocket` extra must fail here with a clear
# message rather than ship an app whose default engine is missing (the v0.8.7 bug).
try:
    pocket_datas, pocket_binaries, pocket_hiddenimports = collect_all("pocket_tts")
except Exception as error:  # noqa: BLE001 - fail loudly with actionable text
    raise SystemExit(
        "Cannot build the release: pocket_tts is not installed in this environment. "
        "Install it with `python -m pip install -e \".[pocket]\"` before running the build."
    ) from error
# Qwen3-TTS is the recommended engine (first entry of the engine selector) and
# faster-whisper provides its local transcription of reference clips. Both must
# be bundled or the packaged app answers "runtime manque" for every engine but
# the default. The release workflow installs the qwen stack (see release.yml); a
# build environment missing it must fail loudly rather than ship a broken app.
try:
    qwen_datas, qwen_binaries, qwen_hiddenimports = collect_all("qwen_tts")
    whisper_datas, whisper_binaries, whisper_hiddenimports = collect_all("faster_whisper")
except Exception as error:  # noqa: BLE001 - fail loudly with actionable text
    raise SystemExit(
        "Cannot build the release: the Qwen3-TTS runtime (qwen-tts / faster-whisper) "
        "is not installed in this environment. Install the tts stack (see "
        "release.yml) before running the build."
    ) from error

datas = [
    (str(SRC / "soundmaster" / "resources"), "soundmaster/resources"),
    *sounddevice_datas,
    *soundfile_datas,
    *pocket_datas,
    *qwen_datas,
    *whisper_datas,
]

hiddenimports = [
    "keyboard",
    *collect_submodules("keyboard"),
    "soundmaster.__main__",
    "soundmaster.resources",
    "torch",
    "torchaudio",
    *sounddevice_hiddenimports,
    *soundfile_hiddenimports,
    *pocket_hiddenimports,
    *qwen_hiddenimports,
    *whisper_hiddenimports,
    *collect_submodules("soundmaster.core"),
    *collect_submodules("soundmaster.ui"),
]

analysis = Analysis(
    [str(SRC / "soundmaster" / "main.py")],
    pathex=[str(SRC)],
    binaries=[
        *sounddevice_binaries,
        *soundfile_binaries,
        *pocket_binaries,
        *qwen_binaries,
        *whisper_binaries,
    ],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SoundMaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "packaging" / "icon.ico"),
)

COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="SoundMaster",
    strip=False,
    upx=False,
)
