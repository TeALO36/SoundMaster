"""SoundMaster application entry point."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# In the packaged windowed app there is no console, so ``sys.stdout`` and
# ``sys.stderr`` are ``None``. huggingface_hub renders its download progress
# bars with tqdm, which writes to those streams and crashes with
# "'NoneType' object has no attribute 'write'". The UI already reports its own
# progress, so disable the library's bars before anything can import it.
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

from PyQt6.QtWidgets import QApplication

from soundmaster.core.config import AppPaths, load_config
from soundmaster.core.legal import load_legal_profile
from soundmaster.core.logger import setup_logging
from soundmaster.resources import get_app_icon
from soundmaster.ui.main_window import MainWindow
from soundmaster.version import __version__

# Mirrors the preference key used by the voice-model settings page.
MODEL_DIRECTORY_PREFERENCE = "model_directory"

# Below this much free space on the default model disk, a first-run install
# (Pocket TTS weights, Qwen/OmniVoice models) is likely to fail, so another
# drive is selected automatically.
AUTO_MODEL_DIR_MIN_SYSTEM_FREE = 8 * 1024**3  # 8 GiB


DRIVE_FIXED = 3  # Win32: local fixed disk (NVMe/HDD), never a network share


def _is_local_fixed_drive(root: Path) -> bool:
    """Whether ``root`` is a local fixed drive and not a network share.

    Network shares (Freebox NAS, Google Drive, …) report huge free space but are
    slow and unreliable for multi-gigabyte model downloads, so they must never
    be auto-selected. Windows classifies them with ``GetDriveTypeW``; on other
    platforms every drive is assumed local (the API is Windows-only).
    """

    if os.name != "nt":
        return True
    try:
        import ctypes

        drive = str(root)[:2]  # e.g. "D:"
        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == DRIVE_FIXED
    except (AttributeError, ImportError, OSError):  # pragma: no cover - win32 API, defensive
        return False


def _auto_model_directory(paths: AppPaths) -> Path | None:
    """Pick the largest other *local* drive when the default disk is too full.

    Returns ``None`` when the default model folder already has enough room or
    when no other suitable local drive exists. Network shares are excluded: a
    NAS looks tempting (huge free space) but makes installs slow and fragile.
    """

    try:
        free = shutil.disk_usage(paths.models).free
    except OSError:
        return None
    if free >= AUTO_MODEL_DIR_MIN_SYSTEM_FREE:
        return None
    default_anchor = Path(paths.models).anchor
    best: tuple[int, Path] | None = None
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:\\")
        if root.anchor == default_anchor:
            continue
        # Ask Windows what kind of drive this is *before* touching it. Probing a
        # mapped network drive that is asleep blocks for the whole SMB timeout,
        # and the drive would be rejected immediately afterwards anyway — that
        # wait is what froze startup on machines with a NAS mapped.
        if not _is_local_fixed_drive(root):
            continue
        try:
            # A failing drive does not merely answer "no": an empty card reader
            # or a dying disk raises (WinError 1117, I/O device error). Left
            # uncaught, one bad drive letter took the whole startup down.
            if not root.exists():
                continue
            candidate_free = shutil.disk_usage(root).free
        except OSError:
            continue
        if best is None or candidate_free > best[0]:
            best = (candidate_free, root / "SoundMaster-models")
    return best[1] if best is not None else None


def configure_hf_environment(paths: AppPaths, *, auto_select: bool = True) -> Path:
    """Redirect the Hugging Face hub cache to the user-chosen model directory.

    Pocket TTS downloads its weights through ``hf_hub_download``, which writes
    into the hub cache — by default ``~/.cache/huggingface/hub`` on the system
    disk (usually C:). When that disk is full, the download fails and Pocket TTS
    cannot install. The model directory is user-configurable (Settings → voice
    models, e.g. ``D:/SoundMaster-models``), so the hub cache is redirected there
    *before* any engine or ``huggingface_hub`` import happens. Without a saved
    choice, a nearly full system disk auto-selects the largest other drive
    (``auto_select=False`` disables that for callers that want the literal
    default). ``HF_HOME`` (the location of the gated repository's login token)
    is deliberately left alone. Returns the cache directory that was selected.
    """

    from soundmaster.core.models import (
        HF_CACHE_SUBDIR,
        model_directory,
        record_hf_cache_default,
        set_model_directory,
    )
    from soundmaster.data.library import SoundLibrary

    library = SoundLibrary(paths.database)
    saved = library.preference(MODEL_DIRECTORY_PREFERENCE, "")
    if saved:
        set_model_directory(Path(saved))
    elif auto_select:
        auto = _auto_model_directory(paths)
        if auto is not None:
            set_model_directory(auto)
            library.set_preference(MODEL_DIRECTORY_PREFERENCE, str(auto))
    hf_cache = model_directory(paths) / HF_CACHE_SUBDIR
    os.environ.setdefault("HF_HUB_CACHE", str(hf_cache))
    record_hf_cache_default(hf_cache)
    return hf_cache


def main() -> int:
    """Start the Step 1 bootstrap application."""

    config, paths = load_config()
    paths.ensure_runtime_directories()
    hf_cache = configure_hf_environment(paths)
    logger = setup_logging(paths.logs)
    logger.info("Hugging Face cache: %s", hf_cache)
    logger.info("Starting %s", config.app_name)
    logger.info("Persistent data directory: %s", paths.data_dir)

    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setApplicationVersion(__version__)
    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    legal_profile = load_legal_profile(paths.legal_profile)
    window = MainWindow(legal_profile, paths.legal_profile, paths, config)
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    exit_code = app.exec()
    logger.info("Application exited with code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
