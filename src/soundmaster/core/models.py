"""Local Hugging Face model management for SoundMaster.

Downloads use the public Hugging Face Hub only. No inference API and no access token
are required for the public repositories configured here. Model licenses must still
be reviewed before commercial redistribution or product bundling.
"""

from __future__ import annotations

import argparse
import errno
import os
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from soundmaster.core.config import AppPaths, load_config

MODEL_DIR_ENV = "SOUNDMASTER_MODEL_DIR"

# Pocket TTS downloads its weights through ``hf_hub_download`` into the
# Hugging Face hub cache. The app redirects that cache under the user-chosen
# model directory (e.g. D:) so a full system disk cannot break installs.
HF_CACHE_SUBDIR = "hf-cache"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    key: str
    repository: str
    directory_name: str
    purpose: str
    approximate_storage: str
    license_reference: str


MODEL_PROFILES: tuple[ModelProfile, ...] = (
    ModelProfile(
        key="pocket-tts",
        repository="kyutai/pocket-tts",
        directory_name="pocket-tts",
        purpose="Clonage vocal ultra-rapide sur CPU (100M paramètres, Kyutai)",
        approximate_storage="~300 Mo",
        license_reference="https://huggingface.co/kyutai/pocket-tts",
    ),
    ModelProfile(
        key="qwen3-tts",
        repository="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        directory_name="Qwen3-TTS-12Hz-1.7B-Base",
        purpose="Haute qualité audio 1.7B (Qwen / Alibaba)",
        approximate_storage="~3,5 Go avec tokenizer",
        license_reference="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    ),
    ModelProfile(
        key="qwen3-tts-0.6b",
        repository="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        directory_name="Qwen3-TTS-12Hz-0.6B-Base",
        purpose="Modèle léger Qwen 0.6B (rapide & empreinte réduite)",
        approximate_storage="~1,2 Go avec tokenizer",
        license_reference="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    ),
    ModelProfile(
        key="qwen3-tts-tokenizer",
        repository="Qwen/Qwen3-TTS-Tokenizer-12Hz",
        directory_name="Qwen3-TTS-Tokenizer-12Hz",
        purpose="Tokenizer audio requis par Qwen3-TTS",
        approximate_storage="~400 Mo",
        license_reference="https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz",
    ),
    ModelProfile(
        key="omnivoice",
        repository="k2-fsa/OmniVoice",
        directory_name="OmniVoice",
        purpose="Clonage multilingue avec ASR automatique (k2-fsa)",
        approximate_storage="~2,2 Go",
        license_reference="https://huggingface.co/k2-fsa/OmniVoice",
    ),
    ModelProfile(
        key="f5-tts",
        repository="SWivid/F5-TTS",
        directory_name="F5-TTS",
        purpose="Clonage expressif avec émotions textuelles (ex: [sad], [happy])",
        approximate_storage="~1,8 Go",
        license_reference="https://huggingface.co/SWivid/F5-TTS",
    ),
)


# The user can pick a model folder at runtime (e.g. on a second disk). It is
# applied through :func:`set_model_directory` and takes precedence over the
# ``SOUNDMASTER_MODEL_DIR`` environment variable so a choice made in the UI is
# never silently overridden by a stale environment variable.
_model_directory_override: Path | None = None


def _default_hf_hub_cache() -> Path:
    """Recompute huggingface_hub's default hub cache from the environment."""

    hf_home = os.path.expandvars(
        os.path.expanduser(
            os.getenv(
                "HF_HOME",
                os.path.join(
                    os.getenv("XDG_CACHE_HOME", str(Path.home() / ".cache")),
                    "huggingface",
                ),
            )
        )
    )
    legacy = os.getenv("HUGGINGFACE_HUB_CACHE", os.path.join(hf_home, "hub"))
    hub_cache = os.path.expandvars(os.path.expanduser(os.getenv("HF_HUB_CACHE", legacy)))
    return Path(hub_cache)

# The hub-cache location chosen at application startup. Resetting the model
# folder mid-session must restore this (the environment alone is not reliable:
# it was mutated by the very change being undone).
_startup_hf_hub_cache: Path | None = None


def record_hf_cache_default(target: Path | None) -> None:
    """Remember the hub-cache location chosen at application startup."""

    global _startup_hf_hub_cache
    _startup_hf_hub_cache = Path(target) if target is not None else None


def _apply_hf_hub_cache_location(target: Path) -> None:
    """Redirect the huggingface_hub hub cache to ``target`` immediately.

    huggingface_hub snapshots the cache path into module constants at import
    time, but ``hf_hub_download`` and ``scan_cache_dir`` read the constants
    live, so patching them makes a folder change effective at once instead of
    only at the next launch. Only the *hub cache* is redirected — ``HF_HOME``
    (which also locates the login token of the gated Pocket TTS repository) is
    deliberately left alone so existing authentication keeps working.
    """

    os.environ["HF_HUB_CACHE"] = str(target)
    try:
        import huggingface_hub.constants as hf_constants
    except ImportError:
        return
    hf_constants.HF_HUB_CACHE = str(target)
    hf_constants.default_cache_path = str(target)


def set_model_directory(directory: Path | None) -> None:
    """Redirect all model storage to ``directory`` (or back to the default)."""

    global _model_directory_override
    _model_directory_override = (
        Path(directory).expanduser().resolve() if directory is not None else None
    )
    target = (
        _model_directory_override / HF_CACHE_SUBDIR
        if _model_directory_override is not None
        else (_startup_hf_hub_cache or _default_hf_hub_cache())
    )
    _apply_hf_hub_cache_location(target)


class ModelDownloadError(RuntimeError):
    """Raised when a public model cannot be downloaded."""


def _download_error_message(repository: str, error: BaseException) -> str:
    """Build an honest download error, with a clear hint on a full disk."""

    message = f"Téléchargement impossible pour {repository}: {error}"
    full = isinstance(error, OSError) and error.errno == errno.ENOSPC
    text = str(error).lower()
    full = full or "no space left on device" in text or "there is not enough space" in text
    if full:
        message += (
            " — Espace disque insuffisant. Libérez de l’espace ou changez le "
            "dossier des modèles dans Paramètres → Modèles vocaux vers un disque "
            "avec de l’espace libre (par exemple D:)."
        )
    return message


def model_directory(paths: AppPaths) -> Path:
    if _model_directory_override is not None:
        return _model_directory_override
    configured = os.environ.get(MODEL_DIR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return paths.models


def get_profile(key: str) -> ModelProfile:
    for profile in MODEL_PROFILES:
        if profile.key == key:
            return profile
    available = ", ".join(profile.key for profile in MODEL_PROFILES)
    raise KeyError(f"Modèle inconnu : {key}. Disponibles : {available}")


def model_path(profile: ModelProfile, paths: AppPaths) -> Path:
    return model_directory(paths) / profile.directory_name


def is_downloaded(profile: ModelProfile, paths: AppPaths) -> bool:
    directory = model_path(profile, paths)
    return directory.is_dir() and any(directory.iterdir())


def model_size_bytes(profile: ModelProfile, paths: AppPaths) -> int:
    """Calculate total size on disk for a downloaded model in bytes."""

    directory = model_path(profile, paths)
    if not (directory.is_dir() and any(directory.iterdir())):
        return 0
    total = 0
    try:
        for file in directory.rglob("*"):
            if file.is_file():
                total += file.stat().st_size
    except OSError:
        pass
    return total


def model_size_str(profile: ModelProfile, paths: AppPaths) -> str:
    """Return a human-readable size for a downloaded model."""

    bytes_size = model_size_bytes(profile, paths)
    if bytes_size <= 0:
        return "Non installé"
    if bytes_size >= 1024**3:
        return f"{bytes_size / (1024**3):.1f} Go"
    return f"{bytes_size / (1024**2):.0f} Mo"


def delete_model(profile: ModelProfile, paths: AppPaths) -> bool:
    """Remove a local model directory to free disk space."""

    import shutil

    directory = model_path(profile, paths)
    if directory.is_dir():
        try:
            shutil.rmtree(directory)
            return True
        except OSError:
            return False
    return False


def download_model(
    profile: ModelProfile,
    paths: AppPaths,
    progress: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Download a public repository into the app's model directory.

    Files are resolved through the Hub metadata API (so the total size is known
    up front) and fetched one by one with ``hf_hub_download``, which resumes
    partial downloads and writes real files into ``local_dir``. ``progress`` is
    invoked after each file with ``(downloaded_bytes, total_bytes, filename)``.
    Passing ``token=None`` makes the no-API-key behavior explicit; private or
    gated repositories are rejected rather than prompting.
    """

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # The packaged app has no console (stdout/stderr are None): tqdm progress
    # bars crash there with "'NoneType' object has no attribute 'write'". The
    # GUI shows its own progress, so never render the library's bars.
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as error:
        raise ModelDownloadError(
            "huggingface_hub manque. Lancez setup_env.bat ou installez l’extra models."
        ) from error

    destination = model_path(profile, paths)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        info = HfApi().model_info(profile.repository, files_metadata=True, token=None)
        files = [
            (sibling.rfilename, int(sibling.size or 0))
            for sibling in info.siblings
            if sibling.rfilename != ".gitattributes"
        ]
    except Exception as error:
        raise ModelDownloadError(_download_error_message(profile.repository, error)) from error

    total = sum(size for _name, size in files)
    downloaded = 0
    try:
        for rfilename, size in files:
            hf_hub_download(
                repo_id=profile.repository,
                filename=rfilename,
                local_dir=str(destination),
                token=None,
            )
            downloaded += size
            if progress is not None:
                progress(downloaded, total, rfilename)
    except Exception as error:
        raise ModelDownloadError(_download_error_message(profile.repository, error)) from error
    return destination


def download_models(keys: Iterable[str], paths: AppPaths) -> list[Path]:
    downloaded: list[Path] = []
    for key in keys:
        profile = get_profile(key)
        print(f"\n[{profile.key}] {profile.repository}")
        print(f"Usage : {profile.purpose}")
        print(f"Dossier : {model_path(profile, paths)}")
        downloaded.append(download_model(profile, paths))
        print(f"Terminé : {downloaded[-1]}")
    return downloaded


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Télécharge les modèles publics SoundMaster depuis Hugging Face, sans API d’inférence."
    )
    parser.add_argument(
        "command",
        choices=("list", "status", "download"),
        nargs="?",
        default="download",
    )
    parser.add_argument(
        "models",
        nargs="*",
        help=(
            "Profils à télécharger : qwen3-tts, qwen3-tts-tokenizer, omnivoice "
            "ou pocket-tts."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _, paths = load_config()
    paths.ensure_runtime_directories()

    if args.command == "list":
        for profile in MODEL_PROFILES:
            print(f"{profile.key}: {profile.repository} — {profile.purpose}")
        return 0

    if args.command == "status":
        root = model_directory(paths)
        print(f"Dossier modèles : {root}")
        for profile in MODEL_PROFILES:
            state = "présent" if is_downloaded(profile, paths) else "absent"
            print(f"{profile.key}: {state} — {model_path(profile, paths)}")
        return 0

    if not args.models:
        parser.error(
            "Indiquez au moins un profil pour éviter un téléchargement accidentel de plusieurs gros modèles. "
            "Exemple : download qwen3-tts"
        )
    invalid_keys = [key for key in args.models if key not in {profile.key for profile in MODEL_PROFILES}]
    if invalid_keys:
        parser.error(f"Profil(s) inconnu(s) : {', '.join(invalid_keys)}")

    keys = args.models
    print("Téléchargement public Hugging Face sans clé API.")
    print("Les modèles peuvent occuper plusieurs dizaines de Go au total.")
    try:
        download_models(keys, paths)
    except (KeyError, ModelDownloadError) as error:
        print(f"ERREUR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
