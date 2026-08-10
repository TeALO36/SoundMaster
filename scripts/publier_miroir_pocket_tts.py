"""Publish a mirror of Kyutai's Pocket TTS weights on your own Hugging Face account.

Why: Kyutai's copy sits behind an access gate, so every SoundMaster user would
have to create a Hugging Face account, accept terms on the website and log in
locally before voice cloning works at all. Pocket TTS is published under
CC-BY-4.0, which permits redistribution and commercial use provided the author is
credited and the licence travels with the copy. This script performs that copy
and writes the required attribution.

What it does NOT do: it does not alter the model, and it does not remove the
acceptable-use commitments. Those are carried by SoundMaster's own consent screen,
which the user must accept before the cloning menu unlocks.

Usage:

    .venv\\Scripts\\python -m huggingface_hub.commands.huggingface_cli login
    .venv\\Scripts\\python scripts/publier_miroir_pocket_tts.py VOTRE-COMPTE/pocket-tts-soundmaster

Add --private to publish a private mirror (your users would then need a token,
which defeats the purpose; only useful for testing).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

UPSTREAM = "kyutai/pocket-tts"
UNGATED = "kyutai/pocket-tts-without-voice-cloning"

MODEL_CARD = """---
license: cc-by-4.0
base_model: kyutai/pocket-tts
tags:
  - text-to-speech
  - voice-cloning
  - mirror
---

# Pocket TTS — miroir pour SoundMaster

Ce dépôt est une **copie non modifiée** des poids de
[`kyutai/pocket-tts`](https://huggingface.co/kyutai/pocket-tts), republiée pour que
les utilisateurs de SoundMaster n'aient pas à créer un compte Hugging Face avant de
pouvoir cloner une voix.

## Crédit

**Pocket TTS © [Kyutai](https://kyutai.org/).** Modèle d'origine :
<https://huggingface.co/kyutai/pocket-tts>. Distribué sous licence
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/), qui autorise la
redistribution et l'usage commercial avec attribution.

Aucune modification n'a été apportée aux poids.

## Conditions d'utilisation

La charte d'usage de Kyutai s'applique toujours. En utilisant ce modèle, vous vous
engagez à respecter les lois applicables et à ne pas vous en servir pour :

- **cloner ou imiter une voix sans le consentement explicite et licite** de la
  personne concernée ;
- produire de la désinformation, des appels frauduleux ou toute tromperie ;
- produire des contenus illicites, diffamatoires, harcelants, discriminatoires,
  haineux ou portant atteinte à la vie privée.

SoundMaster présente ces engagements dans l'application et exige leur acceptation
avant de déverrouiller le clonage de voix.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_id", help="Destination, par exemple VOTRE-COMPTE/pocket-tts-soundmaster")
    parser.add_argument("--private", action="store_true", help="Publier en dépôt privé")
    parser.add_argument(
        "--dry-run", action="store_true", help="Tout préparer sans rien envoyer"
    )
    args = parser.parse_args(argv)

    if not re.match(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$", args.repo_id):
        parser.error("repo_id doit avoir la forme compte/nom")

    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError:
        print("huggingface_hub manque. Lancez setup_env.bat.", file=sys.stderr)
        return 1

    api = HfApi()
    try:
        who = api.whoami()
    except Exception:
        print(
            "Vous n'êtes pas connecté à Hugging Face.\n"
            "Lancez d'abord :\n"
            "  .venv\\Scripts\\python -m huggingface_hub.commands.huggingface_cli login",
            file=sys.stderr,
        )
        return 1
    print(f"Connecté en tant que : {who.get('name')}")

    print(f"Téléchargement de {UPSTREAM} (nécessite d'avoir accepté ses conditions une fois)…")
    try:
        local = snapshot_download(repo_id=UPSTREAM)
    except Exception as error:
        print(
            f"Téléchargement impossible : {error}\n\n"
            f"Ouvrez https://huggingface.co/{UPSTREAM} et acceptez les conditions "
            "avec ce compte, puis relancez. Cette étape n'est nécessaire qu'une "
            "fois, pour vous — vos utilisateurs n'auront rien à faire.",
            file=sys.stderr,
        )
        return 1
    source = Path(local)
    weights = sorted(source.rglob("*.safetensors"))
    print(f"Récupéré : {len(weights)} fichier(s) de poids dans {source}")

    card = source / "README.md"
    original_card = card.read_text(encoding="utf-8") if card.is_file() else ""
    if args.dry_run:
        print("\n--- dry run : rien n'a été envoyé ---")
        print(f"Destination prévue : {args.repo_id} ({'privé' if args.private else 'public'})")
        print(f"Carte de modèle qui serait écrite :\n{MODEL_CARD[:400]}…")
        return 0

    print(f"Création de {args.repo_id}…")
    api.create_repo(args.repo_id, repo_type="model", private=args.private, exist_ok=True)

    print("Envoi des fichiers (plusieurs centaines de Mo)…")
    api.upload_folder(
        repo_id=args.repo_id,
        folder_path=str(source),
        repo_type="model",
        ignore_patterns=[".cache*", "README.md"],
        commit_message="Miroir de kyutai/pocket-tts (CC-BY-4.0)",
    )
    api.upload_file(
        path_or_fileobj=MODEL_CARD.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.repo_id,
        repo_type="model",
        commit_message="Attribution CC-BY-4.0 et charte d'usage",
    )
    if original_card:
        api.upload_file(
            path_or_fileobj=original_card.encode("utf-8"),
            path_in_repo="ORIGINAL_MODEL_CARD.md",
            repo_id=args.repo_id,
            repo_type="model",
            commit_message="Carte de modèle d'origine conservée",
        )

    print(
        f"\nMiroir publié : https://huggingface.co/{args.repo_id}\n\n"
        "Dernière étape — indiquez-le à SoundMaster, au choix :\n"
        f"  • dans Paramètres → Clonage de voix, champ « Source du modèle » ;\n"
        f"  • ou en fixant DEFAULT_MIRROR_REPO = \"{args.repo_id}\" dans "
        "src/soundmaster/core/pocket_mirror.py pour que ce soit le défaut livré.\n"
        f"  • ou via la variable d'environnement SOUNDMASTER_POCKET_MIRROR.\n\n"
        f"Le dépôt {UNGATED} n'a pas besoin d'être copié : il n'est pas verrouillé."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
