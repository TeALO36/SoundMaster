# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the SoundMaster Windows distribution."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

hiddenimports = [
    "soundmaster.__main__",
    *collect_submodules("soundmaster.core"),
    *collect_submodules("soundmaster.ui"),
]

analysis = Analysis(
    [str(SRC / "soundmaster" / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
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
)

COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="SoundMaster",
    strip=False,
    upx=False,
)
