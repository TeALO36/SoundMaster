"""Local Hugging Face model management for SoundMaster.

Downloads use the public Hugging Face Hub only. No inference API and no access token
are required for the public repositories configured here. Model licenses must still
be reviewed before commercial redistribution or product bundling.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from soundmaster.core.config import AppPaths, load_config


MODEL_DIR_ENV = "SOUNDMASTER_MODEL_DIR"


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
        key="qwen3-tts",
        repository="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        directory_name="Qwen3-TTS-12Hz-1.7B-Base",
        purpose="Clonage vocal zero-shot / génération vocale Qwen3-TTS",
        approximate_storage="Plusieurs Go avec le tokenizer et les variantes futures",
        license_reference="https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    ),
    ModelProfile(
        key="qwen3-tts-tokenizer",
        repository="Qwen/Qwen3-TTS-Tokenizer-12Hz",
        directory_name="Qwen3-TTS-Tokenizer-12Hz",
        purpose="Tokenizer audio requis par Qwen3-TTS",
        approximate_storage="Quelques centaines de Mo à plusieurs Go selon la révision",
        license_reference="https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz",
    ),
    ModelProfile(
        key="omnivoice",
        repository="k2-fsa/OmniVoice",
        directory_name="OmniVoice",
        purpose="Alternative locale multilingue pour clonage vocal zero-shot",
        approximate_storage="Plusieurs Go selon les fichiers de la révision",
        license_reference="https://huggingface.co/k2-fsa/OmniVoice",
    ),
)


class ModelDownloadError(RuntimeError):
    """Raised when a public model cannot be downloaded."""


def model_directory(paths: AppPaths) -> Path:
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


def download_model(profile: ModelProfile, paths: AppPaths) -> Path:
    """Download a public repository into the app's model directory.

    ``snapshot_download`` resumes partial downloads and writes the complete snapshot
    into a stable directory. Passing ``token=None`` makes the no-API-key behavior
    explicit; private or gated repositories are rejected rather than prompting.
    """

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise ModelDownloadError(
            "huggingface_hub manque. Lancez setup_env.bat ou installez l’extra models."
        ) from error

    destination = model_path(profile, paths)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(
            repo_id=profile.repository,
            local_dir=str(destination),
            token=None,
        )
    except Exception as error:
        raise ModelDownloadError(
            f"Téléchargement impossible pour {profile.repository}: {error}"
        ) from error
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
        help="Profils à télécharger : qwen3-tts, qwen3-tts-tokenizer ou omnivoice.",
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
