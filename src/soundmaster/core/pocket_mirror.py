"""Load Pocket TTS weights from a mirror instead of Kyutai's gated repository.

Kyutai publishes Pocket TTS under CC-BY-4.0, which permits redistribution and
commercial use with attribution. Their own copy sits behind an access gate, so a
first-time user has to create a Hugging Face account, accept terms on the website
and log in locally before cloning works at all.

Re-publishing the weights under the same licence removes that detour. This module
does not copy anything itself: it rewrites the engine's own configuration so the
weights are fetched from a mirror, using the documented ``config=`` argument of
``TTSModel.load_model``.

The attribution obligations of CC-BY-4.0 travel with the mirror, so the app shows
the credit and the licence, and the acceptable-use commitments the gate used to
present are carried by SoundMaster's own consent screen.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

MIRROR_PREFERENCE_KEY = "pocket_mirror_repo"
MIRROR_ENV = "SOUNDMASTER_POCKET_MIRROR"

# Set this to the mirror published with scripts/publier_miroir_pocket_tts.py to
# make cloning work out of the box, with no Hugging Face account.
DEFAULT_MIRROR_REPO = ""

UPSTREAM_REPO = "kyutai/pocket-tts"
ATTRIBUTION = (
    "Pocket TTS © Kyutai, distribué sous licence CC-BY-4.0 "
    "(https://creativecommons.org/licenses/by/4.0/). "
    "Modèle d’origine : https://huggingface.co/kyutai/pocket-tts"
)

_REPO_ID = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")


def is_valid_repo_id(repo_id: str) -> bool:
    """Accept only a ``owner/name`` Hugging Face identifier."""

    return bool(_REPO_ID.match((repo_id or "").strip()))


def configured_mirror(preference: str | None = None) -> str:
    """Return the mirror to use: preference, then environment, then default."""

    for candidate in (preference, os.environ.get(MIRROR_ENV), DEFAULT_MIRROR_REPO):
        cleaned = (candidate or "").strip()
        if cleaned and is_valid_repo_id(cleaned):
            return cleaned
    return ""


def upstream_config_path(language: str) -> Path | None:
    """Locate the engine's own YAML for a language bundle."""

    try:
        from pocket_tts.utils.config import CONFIGS_DIR
    except ImportError:
        return None
    candidate = Path(CONFIGS_DIR) / f"{language}.yaml"
    return candidate if candidate.is_file() else None


def rewrite_config(text: str, mirror_repo: str) -> str:
    """Point the voice-cloning weights at the mirror.

    Only ``weights_path`` is redirected. The tokenizer and the fallback weights
    already live in Kyutai's ungated repository, so they are left untouched, and
    the pinned revision is dropped because the mirror has its own commits.
    """

    def replace(match: re.Match[str]) -> str:
        return f"{match.group('key')}: hf://{mirror_repo}/{match.group('path')}"

    return re.sub(
        r"(?P<key>^weights_path)\s*:\s*hf://"
        + re.escape(UPSTREAM_REPO)
        + r"/(?P<path>[^\s@]+)(?:@[0-9a-f]+)?\s*$",
        replace,
        text,
        flags=re.MULTILINE,
    )


def mirror_config(language: str, mirror_repo: str, destination_dir: Path) -> Path | None:
    """Write a config for ``language`` whose weights come from ``mirror_repo``.

    Returns ``None`` when the runtime is missing, the language is unknown, or the
    upstream config does not reference the gated repository, so the caller can
    simply fall back to the normal ``language=`` path.
    """

    if not is_valid_repo_id(mirror_repo):
        return None
    source = upstream_config_path(language)
    if source is None:
        return None
    original = source.read_text(encoding="utf-8")
    rewritten = rewrite_config(original, mirror_repo)
    if rewritten == original:
        return None
    destination_dir.mkdir(parents=True, exist_ok=True)
    # The file name encodes the mirror so switching mirrors cannot reuse a stale
    # config, and the engine still sees a plain YAML path.
    safe = mirror_repo.replace("/", "__")
    destination = destination_dir / f"{language}__{safe}.yaml"
    if not destination.is_file() or destination.read_text(encoding="utf-8") != rewritten:
        destination.write_text(rewritten, encoding="utf-8")
    return destination
