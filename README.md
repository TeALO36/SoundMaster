# SoundMaster

SoundMaster est une application Windows locale destinée aux joueurs : soundboard, lecture audio hors ligne, génération vocale locale et routage vers un casque ou un câble audio virtuel.

> **État actuel — v0.2.1 : fondation fonctionnelle validée**
>
> Cette release fournit le socle PyQt6, le tableau de bord, l’explorateur Myinstants intégré, le cache hors ligne, les paramètres de conformité, les raccourcis Windows et la génération Qwen3-TTS locale optionnelle. Les modèles et les runtimes lourds restent téléchargeables séparément.

## Fonctionnalités disponibles

- fenêtre PyQt6 de démarrage en français ;
- centre de paramètres de conformité et de commercialisation ;
- stockage local des paramètres et des journaux ;
- mode installé et mode portable ;
- téléchargement de modèles publics Hugging Face sans API d’inférence ;
- explorateur Myinstants intégré : recherche, test et ajout aux favoris sans ouvrir le site ;
- génération vocale locale Qwen3-TTS ou OmniVoice avec transcription automatique facultative ;
- enregistrement direct d’un échantillon microphone depuis l’écran de clonage ;
- build Windows automatisé avec PyInstaller et installateur Inno Setup ;
- releases GitHub automatiques sur les tags `vMAJOR.MINOR.PATCH`.

## Installation Windows

### Depuis une release

Téléchargez depuis la [release GitHub](https://github.com/TeALO36/SoundMaster/releases) :

- `SoundMaster-v<version>-Setup.exe` pour une installation utilisateur classique ;
- `SoundMaster-v<version>-Portable.zip` pour lancer l’application sans installation.

L’installateur est un **EXE Inno Setup**, pas un MSI. Un MSI WiX pourra être ajouté plus tard pour les déploiements entreprise.

### Depuis les sources

Prérequis : Windows 10 ou 11 et Python 3.11 à 3.14.

```bat
setup_env.bat
lancer_soundmaster.bat
```

`setup_env.bat` crée `.venv` et installe les dépendances de développement et de build. Les runtimes vocaux restent optionnels pour éviter un téléchargement de plusieurs Go au premier démarrage. Pour lancer directement l’environnement existant :

```bat
run_soundmaster.bat
```

### Activer le clonage vocal accessible

Le champ de transcription n’est pas demandé dans le parcours normal. SoundMaster lance automatiquement une transcription locale de l’échantillon avec Faster-Whisper ; le petit bouton **Options avancées** permet uniquement, si besoin, de saisir une transcription manuelle ou de choisir la langue.

Pour une installation CPU, après `setup_env.bat`, installez les runtimes vocaux dans l’environnement virtuel :

```bat
.venv\\Scripts\\python -m pip install -e ".[tts,voice-auto]"
```

Cette commande installe uniquement des composants locaux. Aucun compte, aucune clé API et aucun service d’inférence distant ne sont nécessaires. Le premier lancement de Faster-Whisper peut télécharger son modèle ASR localement.

**Avec un GPU NVIDIA, utilisez plutôt `setup_gpu.bat` et ne relancez pas cette commande ensuite** : l’extra `tts` autorise une wheel PyTorch générique et pourrait remplacer les wheels CUDA. Si vous devez installer un extra après `setup_gpu.bat`, réinstallez ensuite les wheels CUDA alignées avec la commande présente dans ce script.

### Activer l’accélération NVIDIA

Le script dédié installe Qwen3-TTS, Faster-Whisper pour la transcription automatique sans saisie utilisateur, ainsi que les wheels CUDA alignées de PyTorch et TorchAudio :

```bat
setup_gpu.bat
```

Sur cette machine, la configuration validée est `torch 2.11.0+cu126` avec une RTX 4050 Laptop GPU. Le script conserve le repli CPU dans le code si CUDA n’est pas disponible, mais son installation est destinée aux machines équipées d’un pilote NVIDIA récent et nécessite environ 4 à 6 Go d’espace libre pour le runtime CUDA et ses fichiers temporaires. Ne relancez pas `pip install -e ".[tts]"` après `setup_gpu.bat` sans réinstaller ensuite les wheels CUDA, car PyPI peut remettre la version CPU de PyTorch.

Le moteur sélectionne automatiquement `cuda:0` et BF16 sur les GPU compatibles, sinon FP16, puis revient à CPU/FP32 lorsque CUDA n’est pas détecté. La génération s’exécute en mode inférence sans gradients pour réduire la VRAM utilisée.

Pour vérifier l’environnement :

```bat
.venv\\Scripts\\python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

## Modèles vocaux locaux

Le téléchargement se fait avec `huggingface_hub.snapshot_download`. SoundMaster n’appelle pas de service d’inférence distant et les dépôts publics ne nécessitent pas de clé API.

```bat
telecharger_modeles.bat qwen3-tts
telecharger_modeles.bat qwen3-tts-tokenizer
telecharger_modeles.bat omnivoice
statut_modeles.bat
```

Pour télécharger les trois profils :

```bat
telecharger_modeles.bat all
```

Profils configurés :

| Profil | Dépôt | Rôle |
| --- | --- | --- |
| `qwen3-tts` | [`Qwen/Qwen3-TTS-12Hz-1.7B-Base`](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) | Modèle Qwen3-TTS local |
| `qwen3-tts-tokenizer` | [`Qwen/Qwen3-TTS-Tokenizer-12Hz`](https://huggingface.co/Qwen/Qwen3-TTS-Tokenizer-12Hz) | Tokenizer audio Qwen3-TTS |
| `omnivoice` | [`k2-fsa/OmniVoice`](https://huggingface.co/k2-fsa/OmniVoice) | Alternative locale de clonage vocal |

Les poids peuvent occuper plusieurs dizaines de Go. Ils ne sont pas inclus dans GitHub Releases et ne sont jamais commités dans ce dépôt. Le modèle Qwen3-TTS déjà utilisé par le test GPU est stocké dans `%LOCALAPPDATA%\\SoundMaster\\models` sur cette machine. Utilisez un autre disque si nécessaire :

```bat
set SOUNDMASTER_MODEL_DIR=D:\SoundMasterModels
telecharger_modeles.bat qwen3-tts
```

Le bouton de génération permet de choisir Qwen3-TTS ou OmniVoice dans les options avancées. L’auto-transcription est lancée uniquement lorsqu’aucune transcription avancée n’a été fournie. Le bouton d’enregistrement crée un échantillon local de 3 à 10 secondes dans `voice-samples`. Avant toute redistribution, vérifiez la licence, la révision, les notices et les dépendances exactes du modèle utilisé.

## Données locales et confidentialité

Par défaut, les données applicatives sont stockées dans :

```text
%LOCALAPPDATA%\SoundMaster\
```

Le mode portable utilise un dossier `data` à côté de l’exécutable. Les dossiers utilisés sont notamment :

- `soundmaster.db` : données applicatives futures ;
- `legal_profile.json` : configuration locale de conformité ;
- `audio-cache\` : cache audio futur ;
- `voice-samples\` : échantillons vocaux fournis par l’utilisateur ;
- `models\` : modèles téléchargés si `SOUNDMASTER_MODEL_DIR` n’est pas défini ;
- `logs\` : journaux locaux.

Les échantillons vocaux peuvent constituer des données personnelles ou biométriques selon leur usage et la juridiction concernée. Ne fournissez pas la voix d’une autre personne sans autorisation appropriée. Le centre de conformité aide à documenter les décisions de l’éditeur ; il ne constitue ni un avis juridique ni une certification.

## Build et releases

Build local Windows :

```powershell
python -m pip install ".[dev,build]"
.\packaging\build_windows.ps1 -Version 0.2.1
```

Le workflow `.github/workflows/release.yml` s’exécute lorsqu’un tag comme `v0.2.1` est poussé. Il lance les tests, construit le ZIP portable et l’installateur, puis les joint à une GitHub Release.

```powershell
git tag v0.2.0
git push origin v0.2.0
```

Les artefacts publiés sont actuellement non signés. Pour une distribution Windows commerciale, configurez une signature Authenticode avec un certificat conservé dans un secret ou un service de signature. Ne committez jamais de clé privée.

## Développement

```bat
.venv\Scripts\python -m compileall src tests
.venv\Scripts\ruff check src tests
.venv\Scripts\pytest
```

## Licences et contenus tiers

Le code original de SoundMaster est distribué sous licence MIT. Cette licence ne s’étend pas automatiquement aux dépendances, aux modèles, aux poids, aux voix, aux sons ou aux contenus téléchargés par l’utilisateur.

- Consultez [`LICENSE`](LICENSE) pour le code original du projet.
- Consultez [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) pour les références de conformité connues.
- Les modèles Qwen3-TTS et OmniVoice doivent être vérifiés selon la révision réellement utilisée.
- Les fichiers téléchargés depuis Myinstants ne doivent pas être présentés comme libres de droits. Les conditions du site indiquent un usage personnel et non commercial ; n’intégrez ni ne redistribuez ces sons commercialement sans autorisations écrites et vérification des droits des œuvres sous-jacentes.
- Les utilisateurs sont responsables des droits liés aux voix, échantillons audio et fichiers ajoutés à SoundMaster.

La présence d’une référence dans ce dépôt ne constitue pas une garantie de compatibilité commerciale. L’éditeur doit faire auditer les licences et les droits applicables aux marchés visés avant toute vente ou redistribution.

## Feuille de route

1. shell PyQt6 français, sidebar et tray ;
2. routage audio casque / câble virtuel ;
3. explorateur Myinstants avec cache hors ligne et contrôle des droits ;
4. moteurs Qwen3-TTS / OmniVoice locaux, enregistrement microphone et historique des générations ;
5. raccourcis globaux ;
6. dashboard, favoris et historique.

## Sources utiles

- [Dépôt SoundMaster](https://github.com/TeALO36/SoundMaster)
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- [Qwen3-TTS — modèle Hugging Face](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base)
- [OmniVoice](https://github.com/k2-fsa/OmniVoice)
- [Conditions Myinstants](https://www.myinstants.com/en/terms_of_use.html)
- [CNIL — systèmes d’IA et RGPD](https://www.cnil.fr/en/ai-system-development-cnils-recommendations-to-comply-gdpr)
- [Règlement européen sur l’IA](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)
