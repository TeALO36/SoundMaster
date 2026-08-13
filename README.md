# SoundMaster

SoundMaster est une application Windows locale destinée aux joueurs : soundboard, lecture audio hors ligne, génération vocale locale et routage vers un casque ou un câble audio virtuel.

> **État actuel — v0.7.0 : icône officielle d’application, clonage sans compte, prêt à l’emploi, latence réduite et mises à jour intégrées**
>
> Cette release fournit le socle PyQt6, le tableau de bord, l’explorateur Myinstants intégré, le cache hors ligne, les paramètres de conformité, les raccourcis Windows et la génération Qwen3-TTS locale optionnelle. Les modèles et les runtimes lourds restent téléchargeables séparément.

## Fonctionnalités disponibles

- fenêtre PyQt6 de démarrage en français ;
- centre de paramètres de conformité et de commercialisation ;
- stockage local des paramètres et des journaux ;
- mode installé et mode portable ;
- téléchargement de modèles publics Hugging Face sans API d’inférence ;
- explorateur Myinstants intégré : catalogue, recherche et aperçu en direct sans ouvrir le site ; seuls les favoris sont téléchargés pour le mode hors ligne et les raccourcis ;
- clonage de voix en trois étapes avec écoute intégrée de l’échantillon et du résultat ;
- moteur **Pocket TTS** (Kyutai) par défaut : génération rapide sur processeur, sans GPU et sans transcription, en 6 langues ;
- lecture quasi instantanée des sons grâce au préchargement au survol et aux lecteurs dédiés aux raccourcis ;
- vérification et installation des mises à jour depuis les paramètres ;
- génération vocale locale Qwen3-TTS ou OmniVoice avec transcription automatique facultative ;
- enregistrement direct d’un échantillon microphone depuis l’écran de clonage ;
- conditions d’utilisation du clonage acceptables et révocables à tout moment depuis les paramètres ;
- build Windows automatisé avec PyInstaller et installateur Inno Setup ;
- releases GitHub automatiques sur les tags `vMAJOR.MINOR.PATCH`.

## Cloner une voix

Le menu **Clonage de voix** reste verrouillé tant que ses conditions d’utilisation
n’ont pas été acceptées dans **Paramètres → Clonage de voix**. Cliquer sur l’entrée
verrouillée ouvre directement ces conditions, qui rappellent que vous devez disposer
de l’accord de la personne concernée et que **l’éditeur de SoundMaster n’est pas
responsable** de l’usage que vous faites de la fonction. Décocher la case reverrouille
le menu immédiatement.

Une fois déverrouillé, l’écran suit trois étapes :

1. **Choisissez une voix** — sélectionnez une voix existante ou créez-en une nouvelle,
   puis nommez-la. L’enregistrement de la voix est facultatif pour générer : il sert à
   la réutiliser plus tard.
2. **Donnez-lui une voix à imiter** — enregistrez 3 à 10 secondes au micro, capturez la
   sortie Windows, ou importez un fichier. L’échantillon se charge dans le lecteur
   intégré : cliquez sur ▶ pour le réécouter autant de fois que nécessaire. Rien
   n’est joué sans que vous le demandiez.
3. **Écrivez et générez** — saisissez le texte à l’étape 3 puis cliquez sur **Générer**.
   Le résultat s’écoute dans la carte Résultat et peut être réessayé autant de fois
   que nécessaire avant d’être ajouté aux favoris.

Le résultat s’écoute dans la carte **Résultat**, d’où il peut être ajouté aux favoris ou
ouvert dans l’explorateur Windows. Un double-clic sur une ligne de l’historique la
rejoue. Les réglages fins (moteur, langue, température, vitesse, top-p, anti-répétition,
transcription manuelle, sortie à capturer) restent repliés sous **Réglages avancés**.

Avec **F5-TTS**, la palette colorée **Émotions F5-TTS** apparaît au-dessus de la zone
de texte. Cliquez sur une émotion puis sélectionnez la portion concernée : la couleur
est conservée dans l’éditeur et SoundMaster convertit automatiquement ces passages en
balises `[calm]`, `[happy]`, `[sad]`, `[angry]`, `[disgust]` ou `[fearful]` au moment de
la génération. Sélectionner à nouveau un passage avec la même émotion retire sa couleur.
Le texte affiché reste donc lisible et ne contient jamais les balises techniques.

## Installation Windows

### Depuis une release

Téléchargez depuis la [release GitHub](https://github.com/TeALO36/SoundMaster/releases) :

- `SoundMaster-v<version>-Setup.exe` pour une installation utilisateur classique ;
- `SoundMaster-v<version>-Portable.zip` pour lancer l’application sans installation.

L’installateur est un **EXE Inno Setup**, pas un MSI. Un MSI WiX pourra être ajouté plus tard pour les déploiements entreprise ; l’updater intégré le préférera automatiquement à l’EXE dès qu’il sera publié.

### Mettre à jour

**Paramètres → Mises à jour → Vérifier les mises à jour** interroge la liste publique
des releases GitHub. SoundMaster ne se met jamais à jour tout seul en arrière-plan et
n’envoie aucune donnée : seule la release la plus récente est lue, et rien n’est
téléchargé sans confirmation.

Le fichier proposé dépend de la façon dont l’application a été installée :

| Mode | Fichier téléchargé | Comportement |
| --- | --- | --- |
| Installation Windows | `.msi` s’il existe, sinon `SoundMaster-v<version>-Setup.exe` | L’installateur est lancé et SoundMaster se ferme pour se laisser remplacer |
| Portable | `SoundMaster-v<version>-Portable.zip` | L’archive est révélée dans l’explorateur ; remplacez le dossier portable manuellement |
| Sources | aucun | La page de la release s’ouvre ; mettez à jour avec `git pull` |

Un téléchargement dont la taille ne correspond pas à celle annoncée par GitHub est
rejeté, et les fichiers servis autrement qu’en HTTPS sont ignorés.

### Depuis les sources

Prérequis : Windows 10 ou 11 et Python 3.11 à 3.14.

```bat
setup_env.bat
lancer_soundmaster.bat
```

`setup_env.bat` crée `.venv` et installe les dépendances de développement, de build et de raccourcis Windows. Les runtimes vocaux restent optionnels pour éviter un téléchargement de plusieurs Go au premier démarrage. Si une ancienne `.venv` affiche « module keyboard manquant », relancez simplement `setup_env.bat` : l’installation est réparée automatiquement. Pour lancer directement l’environnement existant :

```bat
run_soundmaster.bat
```

### Activer le clonage vocal

Le moteur par défaut est **Pocket TTS** (Kyutai) : environ 100 M de paramètres, il tourne sur le processeur et ne demande **aucune transcription**. C’est le chemin le plus rapide, et il ne demande qu’un seul extra :

```bat
.venv\\Scripts\\python -m pip install -e ".[pocket]"
```

#### Autoriser le clonage

Les poids capables d’**imiter votre échantillon** sont dans un dépôt Hugging Face à
accès contrôlé. Sans autorisation, Pocket TTS se rabat silencieusement sur une version
qui ne sait lire que son propre catalogue de voix, et le clonage échoue. Deux options.

**Option A — miroir public ou officiel.** SoundMaster peut télécharger les poids depuis un miroir public ou un dépôt de votre choix : **aucun compte ni jeton nécessaire.**

Pourquoi c’est permis : Pocket TTS est sous licence **CC-BY-4.0**, qui autorise
explicitement la redistribution et l’usage commercial à condition de créditer
l’auteur et de joindre la licence. Le verrou est une couche d’accès que Kyutai
ajoute sur sa propre copie, pas une restriction de la licence.

Pour publier un miroir, une seule commande à lancer une fois
par le développeur — jamais par les utilisateurs :

```bat
.venv\Scripts\python -m huggingface_hub.commands.huggingface_cli login
.venv\Scripts\python scripts/publier_miroir_pocket_tts.py VOTRE-COMPTE/pocket-tts-soundmaster
```

Le script copie les poids sans les modifier et écrit la carte de modèle avec
l’attribution à Kyutai, la licence et la charte d’usage. Vous pouvez fixer la variable
d'environnement `SOUNDMASTER_POCKET_MIRROR` ou `DEFAULT_MIRROR_REPO` dans `src/soundmaster/core/pocket_mirror.py`.

Deux obligations vous incombent alors, et l’application les assume déjà :
l’**attribution** (affichée sous les conditions d’utilisation) et la **charte d’usage**
que le verrou de Kyutai servait à faire lire — pas d’imitation sans consentement
explicite, pas de fraude — reprise dans l’écran de consentement de SoundMaster.
Ce n’est pas un avis juridique : faites relire avant une commercialisation.

**Option B — utiliser le dépôt officiel.** Chaque utilisateur ouvre
[huggingface.co/kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts), accepte
les conditions (approbation immédiate), crée un jeton sur
[settings/tokens](https://huggingface.co/settings/tokens) puis se connecte :

```bat
.venv\Scripts\python -m huggingface_hub.commands.huggingface_cli login
```

Si l’accès manque, SoundMaster affiche ces instructions au lieu d’une erreur brute.
Hugging Face n’expose aucune API permettant d’accepter ces conditions depuis
l’application : c’est précisément ce que l’option A évite.

#### Langues et vitesse

Pocket TTS publie **un modèle par langue** : anglais, français, allemand, espagnol,
italien et portugais. Choisissez-la dans **Réglages avancés → Langue**. Attention, les
variantes ne sont pas uniformes : **le français n’existe qu’en modèle 24 couches**
(la case *Modèle haute qualité* est donc sans effet et grisée), tandis que l’anglais
n’a pas de variante 24 couches. Allemand, espagnol, italien et portugais ont les deux.

SoundMaster choisit automatiquement le chemin le plus rapide disponible. Mesures
réelles sur ce projet (RTX 4050, modèle français 24 couches, ~8 s de parole générée) :

| Configuration | Durée de génération |
| --- | --- |
| Processeur seul | 11,5 s |
| Processeur + quantification | 9,6 s |
| **Carte graphique (choisie automatiquement)** | **8,8 s** |

La case **Génération accélérée** n’a donc d’effet que sur une machine sans GPU : avec
une carte graphique, elle est ignorée, car un modèle quantifié ne peut pas s’exécuter
sur le GPU et serait plus lent. Langue, température et quantification sont fixées au
chargement du moteur : en changer une le recharge (quelques secondes).

Une fois le moteur et la voix en mémoire, une génération coûte environ **le temps réel
de l’audio produit** (7 s de parole en ~7 s), et regénérer avec la même voix ne
recharge rien.

Les moteurs Qwen3-TTS et OmniVoice restent disponibles dans **Réglages avancés** pour une qualité maximale. Ceux-là ont besoin d’une transcription de l’échantillon : SoundMaster la produit automatiquement en local avec Faster-Whisper, et le champ **Transcription** ne sert qu’à la saisir à la main si besoin.

Pocket TTS (le moteur par défaut) fait partie de l’installation de base (`setup_env.bat` installe l’extra `pocket`) et est embarqué dans les builds publiés.

Pour une installation CPU, après `setup_env.bat`, installez ces runtimes plus lourds dans l’environnement virtuel :

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

Le téléchargement se fait avec `huggingface_hub` (résolution des fichiers via l’API du Hub, puis `hf_hub_download` fichier par fichier, avec reprise des téléchargements partiels et progression affichée dans l’application). SoundMaster n’appelle pas de service d’inférence distant et les dépôts publics ne nécessitent pas de clé API. Le dossier de stockage des modèles est choisi dans Paramètres → Modèles vocaux (par défaut `%LOCALAPPDATA%\SoundMaster\models`).

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
| `pocket-tts` | [`kyutai/pocket-tts`](https://huggingface.co/kyutai/pocket-tts) | Clonage vocal rapide sur CPU (100 M paramètres) |

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

La capture de sortie audio utilise le backend Windows WASAPI via `sounddevice`. Si le bouton est inactif ou si la capture échoue, relancez `setup_env.bat`, vérifiez que la sortie sélectionnée est bien un périphérique Windows (casque, haut-parleurs ou câble virtuel), puis réessayez. La première capture peut aussi échouer si aucune sortie WASAPI n’est disponible.

## Build et releases

Build local Windows :

```powershell
python -m pip install ".[dev,build]"
.\packaging\build_windows.ps1 -Version 0.6.1
```

Le workflow `.github/workflows/release.yml` s’exécute lorsqu’un tag comme `v0.6.1` est poussé. Il lance les tests, construit le ZIP portable et l’installateur, puis les joint à une GitHub Release.

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
3. explorateur Myinstants avec aperçu en direct, favoris téléchargés pour le cache hors ligne et contrôle des droits ;
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
