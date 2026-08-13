# Changelog

## 0.9.2 — 2026-08-13

### Fixed

- **« La langue french_24l n’est pas disponible pour Pocket TTS dans cette version »** : le message était un **faux diagnostic**. Quand le disque système (C:) est plein, le téléchargement des poids Pocket TTS échoue avec une `OSError` dont le *chemin* contient `french_24l` (…/languages/french_24l/model.safetensors) — l’ancien détecteur matchait ce nom dans le chemin et accusait la langue à tort. La détection est maintenant stricte (seules les vraies erreurs de langue du runtime déclenchent ce message), et un **disque plein est signalé comme tel** avec une aide concrète (libérer de l’espace ou changer le dossier des modèles vers un disque libre, ex. D:).
- **Les téléchargements Pocket TTS tombent maintenant sur le disque choisi** : le cache Hugging Face (`HF_HUB_CACHE`) est redirigé sous le dossier des modèles (ex. `D:\SoundMaster-models\hf-cache`) avant tout import de `huggingface_hub`, au démarrage et à chaque changement de dossier en cours de session. `HF_HOME` (emplacement du jeton de connexion du dépôt gated Kyutai) est volontairement inchangé pour ne pas casser le clonage vocal.
- **Sélection automatique d’un autre disque** : sans choix explicite de l’utilisateur, si le disque par défaut des modèles a moins de 8 Go libres, l’application choisit automatiquement le plus grand autre disque local (ex. `D:\SoundMaster-models`), le mémorise et y redirige les téléchargements — une installation sur une machine au C: saturé fonctionne sans intervention.
- L’erreur de téléchargement des autres modèles (Qwen3-TTS, OmniVoice, F5-TTS) signale aussi clairement un disque plein quand c’est la cause.
- **« Le runtime qwen-tts manque » dans l’application installée** : les moteurs Qwen3-TTS / OmniVoice / F5-TTS n’ont jamais été embarqués dans le binaire (l’extra `tts` était inrésolvable — conflit `transformers==4.57.3` de qwen-tts contre `>=5.3.0` d’omnivoice — donc le build installait seulement Pocket TTS). L’extra `tts` est réparé (stack Qwen3-TTS uniquement, chaque moteur garde son propre environnement), le workflow de release installe désormais `qwen-tts` + `transformers` + `faster-whisper` + **torch CPU** (les wheels CUDA feraient dépasser la limite GitHub de 2 Go par asset), et le spec PyInstaller collecte `qwen_tts`, `faster_whisper` et `torch`/`torchaudio`.
- **Les contrôles de runtime sont fiables** : chaque moteur est maintenant sondé par son propre paquet (`qwen_tts`, `pocket_tts`, …) via `find_spec` au lieu de tester `import torch` — omnivoice ne passe plus pour installé juste parce que torch est présent.

- **Génération Qwen3-TTS avec une langue sélectionnée** : le moteur rejette le token capitalisé de l’UI (`French`) avec `Unsupported languages` — il n’accepte que les codes ISO (`french`, `auto`). La langue est normalisée avant l’appel (`French → french`, `Auto → auto`, …), découvert et vérifié par un clonage réel de bout en bout avec les échantillons Screenrecorder.
- **Auto-sélection du disque des modèles** : un lecteur réseau mappé (NAS Freebox, Google Drive — `DriveType 4`) était choisi à la place du disque local NVMe parce qu’il annonce énormément d’espace libre, envoyant les téléchargements multi-Go sur le réseau. Seuls les disques locaux fixes (`DriveType 3`) sont désormais éligibles.

### Added

- **Import d’un échantillon vocal audio OU vidéo** : le dialogue d’import accepte les vidéos (MP4, MKV, MOV, AVI, WebM, WMV, FLV, MPG, TS, 3GP, …) en plus des formats audio. Une vidéo est convertie en WAV 24 kHz mono **automatiquement** (décodage via PyAV/FFmpeg) — l’utilisateur n’a jamais à convertir quoi que ce soit : il choisit son fichier et l’échantillon est prêt à l’emploi, dans le même lecteur et le même flux de clonage.
- **Soundboard : import d’une vidéo dans les favoris** — le bouton « + Ajouter un fichier » accepte aussi les vidéos : elles sont converties en WAV automatiquement dans le cache (le moteur zéro-latence lit des fichiers audio), puis jouables comme n’importe quel favori.

### Validation

- 160 tests automatisés (21 nouveaux) : le faux diagnostic disque-plein/langue est verrouillé, la détection ENOSPC marche à travers les chaînes d’exceptions, la redirection du cache suit le dossier choisi et se réinitialise correctement, le cache n’écrase jamais un `HF_HUB_CACHE` défini par l’utilisateur, la sélection automatique d’un autre disque est persistée, le spec embarque la stack Qwen, les sondes de runtime vérifient les vrais paquets, la langue Qwen est normalisée vers les codes ISO, le NAS n’est jamais sélectionné, et l’import vidéo convertit bien en WAV (module + interface).

## 0.9.1 — 2026-08-13

### Added

- **Barre de progression des téléchargements avec pourcentage** : les téléchargements de modèles (Qwen3-TTS, OmniVoice, F5-TTS…) affichent maintenant une vraie progression — pourcentage, octets téléchargés sur le total et nom du fichier en cours — dans Paramètres → Modèles vocaux. L’installation de Pocket TTS affiche une barre indéterminée (ses poids sont téléchargés par le runtime lui-même, sans callback d’octets).
- **Dossier des modèles configurable** : une ligne « Dossier des modèles » dans Paramètres → Modèles vocaux permet de choisir le disque/dossier où stocker les modèles (ex. `D:\SoundMaster-models`), avec l’espace libre affiché, un bouton « Réinitialiser » pour revenir au dossier par défaut, et le choix conservé d’une session à l’autre.

### Fixed

- **« Téléchargement impossible pour Qwen/Qwen3-TTS-12Hz-0.6B-Base: 'NoneType' object has no attribute 'write' »** : dans l’application empaquetée (sans console), `sys.stdout`/`sys.stderr` sont `None`, et les barres de progression de `huggingface_hub` (tqdm) écrivent dessus — ce qui faisait échouer **tout** téléchargement de modèle au premier octet. Les barres de la bibliothèque sont désormais désactivées (`HF_HUB_DISABLE_PROGRESS_BARS=1`) au démarrage de l’application et dans `download_model` ; l’interface affiche son propre statut, et les poids Pocket TTS (qui utilisent aussi `hf_hub_download`) sont couverts par le même correctif.
- **« Téléchargement impossible pour SWAC/F5-TTS: 404 Repository Not Found »** : le dépôt `SWAC/F5-TTS` n’existe pas sur Hugging Face — le vrai dépôt officiel est `SWivid/F5-TTS`. F5-TTS pouvait donc **jamais** s’installer ; il est corrigé.
- Le téléchargement passe de `snapshot_download` à une résolution fichier par fichier (`HfApi.model_info` + `hf_hub_download`) : c’est ce qui permet la progression en octets, et la reprise des téléchargements partiels est conservée.

### Validation

- 140 tests automatisés (5 nouveaux : le dépôt F5 pointe vers `SWivid/F5-TTS`, le dossier des modèles est redéfinissable à l’exécution et dans l’interface, la progression en octets est rapportée fichier par fichier, et la barre de progression affiche le pourcentage). Vérification réelle effectuée sur le disque D : téléchargement complet d’un dépôt avec progression (0 % → 100 %) dans `D:\…`, même avec `stdout`/`stderr` nuls (conditions de l’app empaquetée).

## 0.9.0 — 2026-08-13

### Added

- **Installation et réinstallation de Pocket TTS depuis l’application** : la carte du moteur par défaut dans Paramètres → Modèles vocaux affiche désormais un bouton « Installer Pocket TTS » (ou « Réinstaller les poids » quand les poids sont déjà en cache) — toujours disponible, même quand Pocket TTS est le moteur actif par défaut. Le clic lance un vrai téléchargement des poids (~300 Mo) via le chargeur du moteur, puis vérifie dans le cache Hugging Face que les poids de clonage vocal (dépôt gated Kyutai) sont réellement présents : si l’accès au modèle n’a pas été accepté, un message clair explique les étapes (accepter les conditions, créer un jeton, `huggingface-cli login`). La carte montre aussi un statut honnête (« Runtime : intégré · Poids vocaux : installés / à télécharger ») au lieu d’afficher toujours « Non installé ». Choisir Pocket TTS par défaut sans poids téléchargés propose maintenant l’installation immédiatement.

### Changed

- **Le bouton « Tester la voix » est supprimé** : tester la voix revenait à lancer une génération courte — l’utilisateur peut simplement écrire une phrase et cliquer « Générer », puis réécouter et recommencer si besoin. Une génération de moins pour le même résultat.

### Validation

- 133 tests automatisés passent (4 nouveaux : la carte Pocket TTS propose toujours installer/réinstaller, un runtime manquant produit un message clair, l’installation lance bien un téléchargement en arrière-plan, et `preload_pocket_tts` charge puis libère le moteur).

## 0.8.9 — 2026-08-13

### Added

- **Proposition d’installation d’un câble virtuel** dans Paramètres → Audio et système : si aucune sortie « câble » (VB-CABLE ou équivalent) n’est détectée, l’application l’indique clairement et propose un bouton « Installer VB-CABLE (gratuit, officiel) » qui ouvre la page officielle de téléchargement, plus un bouton « Actualiser les périphériques » pour re-scanner sans redémarrer une fois le câble installé. Dès qu’un câble est détecté, l’offre disparaît et le câble apparaît dans la liste « Sortie 2 ».

### Changed

- La page **Conformité éditeur** est maintenant pré-remplie au maximum : identité complète de l’éditeur (projet open source, e-mail de contact `teanokry@gmail.com`, hébergeur GitHub, adresse vers le dépôt), tous les documents pointés vers le dépôt public, licence/revision du modèle Qwen exactes (révision `fd4b254389122332181a7c3db7f27e918eec64e3` vérifiée sur l’API Hugging Face), et cases déjà cochées pour tout ce que le build garantit réellement (identité vérifiée, transparence IA, consentement vocal, licence Qwen, télémétrie optionnelle). L’utilisateur final n’a plus **rien** à remplir pour utiliser l’application ; ne restent ouverts que les éléments qui relèvent exclusivement de l’éditeur (revue juridique externe, SHA-256 du build distribué, CGV/RGPD, droits des audios tiers).

## 0.8.8 — 2026-08-13

### Fixed

- **L’application installée demandait d’installer le modèle OmniVoice alors que Pocket TTS est le moteur par défaut** : le binaire publié n’embarquait pas `pocket_tts` (l’extra `pocket` n’était pas installé au moment du build), donc le moteur par défaut semblait absent, et le repli automatique basculait silencieusement sur OmniVoice — dont le modèle n’est pas téléchargé non plus. Le spec PyInstaller collecte désormais `pocket_tts` explicitement, `setup_env.bat` et le workflow de release installent l’extra `pocket`, et le repli de génération ne bascule plus **jamais** vers un moteur dont le runtime n’est pas installé : si aucun moteur n’est disponible, l’application explique clairement lequel manque au lieu de demander un modèle étranger.
- **La molette de la souris changeait la sélection des listes (modèle, langue…) quand le curseur passait dessus** : en scrollant la page, survoler un menu déroulant faisait défiler ses options sans que l’utilisateur ne le demande. Les listes déroulantes ignorent désormais la molette quand leur popup est fermée — la molette continue de faire défiler la page.
- **Le bouton « ■ Stop » restait affiché à l’infini après la fin d’un son** (tableau de bord, favoris) : ces sons passent par le moteur audio zéro-latence, dont le flux persistant ne signalait jamais la fin de lecture — seule la bascule QMediaPlayer le faisait. Le moteur notifie désormais la fin de la file de lecture (callback transmis au thread UI par signal Qt), le bouton revient à « ▶ Tester », et « ■ Stop » arrête aussi réellement le moteur zéro-latence (pas seulement le lecteur de secours).

### Validation

- 127 tests automatisés passent, dont 7 nouveaux : le spec embarque le moteur par défaut, le repli ne bascule jamais vers un moteur sans runtime, le repli choisit la première alternative réellement installée, les listes déroulantes ignorent la molette, la fin de lecture libère l’état « Stop », « Stop » arrête bien le moteur zéro-latence, et le moteur signale la fin sans la déclencher sur un arrêt manuel.

## 0.8.7 — 2026-08-12

### Fixed

- **« Appliquer et enregistrer » (Audio et système) plantait à chaque clic** : le code appelait `FastAudioEngine.set_devices()` qui n’existait pas. La sortie 2 est désormais optionnelle — plus aucune erreur « Sélectionnez deux périphériques distincts », et « Aucun (désactivé) » est le choix par défaut, donc un utilisateur sans câble virtuel n’est plus bloqué ni forcé d’en installer un.
- **Latence de lecture des soundboards (~2 s)** : `soundfile` (décodage WAV/MP3/OGG/FLAC) n’était pas une dépendance de base, donc le moteur zéro-latence échouait silencieusement et tout retombait sur QMediaPlayer, lent à démarrer. `soundfile` est désormais dans les dépendances de base, le cache PCM est préchargé dès le survol **et pour les sons récents**, et `play()` signale un échec (au lieu d’un silence) quand le flux audio est mort, pour basculer proprement sur QMediaPlayer.
- **Latence audible encore réduite** : mesurée à ~100 ms (5–11 ms de callback + ~90 ms de tampon WASAPI). Le flux utilise désormais `latency="low"` (tampon matériel divisé par deux, ~180 → ~90 ms) et un flux de sortie mort est **rouvert automatiquement en arrière-plan** (au lieu de bloquer l’interface ~0,5–1 s à chaque clic puis de retomber sur QMediaPlayer). Un script `scripts/mesurer_latence_lecture.py` décompose et mesure ces délais.
- **Diagnostic GPU/clonage alarmiste sur une installation saine** : il ne vérifiait que le runtime Qwen3-TTS et affichait « runtime incomplet », « modèle absent », « PyTorch absent ». Il rend désormais compte du moteur par défaut (Pocket TTS, CPU sans PyTorch), détecte **AMD/ROCm** en plus de NVIDIA/CUDA, et n’indique les actions que lorsqu’elles sont réellement nécessaires.
- Le bouton des raccourcis s’appelle maintenant **« Activer les raccourcis » / « Désactiver les raccourcis »** au lieu de « Activer dans Windows ».

### Added

- **Langue par défaut globale** dans Paramètres → Clonage de voix. Choisie une seule fois, elle s’applique à tous les moteurs : Pocket TTS charge son modèle dédié (français, anglais, etc.), Qwen3-TTS et OmniVoice l’utilisent à la génération, et « Auto » laisse chaque moteur choisir. Les nouvelles voix et la page de clonage démarrent sur cette langue, tout en gardant la possibilité de la surcharger voix par voix.

### Changed

- La page **Conformité éditeur** est pré-remplie avec l’identité du projet open source (nom, dépôt GitHub, références des licences) : l’utilisateur final n’a plus rien à remplir pour utiliser l’application. Un script `setup_amd.bat` installe PyTorch ROCm pour les GPU AMD.

### Validation

- 118 tests automatisés passent (dont de nouveaux tests : moteur audio basse latence, auto-rétablissement du flux, routage des favoris via FastAudioEngine, langue par défaut globale, détection AMD/ROCm, conformité pré-remplie).
- Test de bout en bout réel : échantillon vocal français généré avec Windows SAPI, cloné avec le vrai moteur Pocket TTS via le service de l’application (sortie WAV valide).

## 0.8.6 — 2026-08-12

### Fixed

- Declared NumPy as a runtime dependency for the low-latency audio engine so clean Windows release environments can run the test suite and build successfully.
- Kept the release workflow compatible with the existing `v0.8.2`–`v0.8.5` tags, allowing their Windows artifacts to be republished.

## 0.7.0 — 2026-08-11

### Added

- **Icône officielle de l’application.** SoundMaster s’équipe d’un logo haute définition au style audio studio / néon.
- L’icône est désormais appliquée à la fenêtre PyQt6, aux raccourcis Windows, au menu de la zone de notification (system tray), à l’exécutable `SoundMaster.exe` et à l’installateur Inno Setup.

## 0.6.1 — 2026-08-10

### Changed

- The Pocket TTS mirror is now published and shipped as the default source, so voice cloning works on a fresh install with **no Hugging Face account and no terms to accept on a third-party site**. Clearing the field in **Paramètres → Clonage de voix → Source du modèle** restores Kyutai's gated repository.
- The mirror carries only the twelve per-language cloning weights (4.9 GB) rather than the whole 9.8 GB repository: the predefined-voice embeddings that make up the rest are already served from Kyutai's ungated copy, so mirroring them would have doubled the upload for nothing.

### Validation

- 104 automated tests passed; ruff and compilation clean.
- Verified as a new user would experience it: a subprocess with **no Hugging Face token and an empty cache** downloaded the weights from the mirror and cloned the reference voice successfully (timbre 0.992).
- Full click-by-click journey re-run through the real window against the shipped default: test, generation, playback, favorite, dashboard, regeneration — warm generation at roughly real time, timbre 0.985–0.994.

## 0.6.0 — 2026-08-09

### Added

- **Mirror support for the Pocket TTS weights.** Kyutai's copy sits behind an access gate, so a first-time user had to create a Hugging Face account, accept terms on a website and log in locally before cloning worked at all. Pocket TTS is published under CC-BY-4.0, which permits redistribution and commercial use with attribution, so the weights can be re-published on your own account and served without any gate. Point SoundMaster at the mirror in **Paramètres → Clonage de voix → Source du modèle**, through `SOUNDMASTER_POCKET_MIRROR`, or by setting `DEFAULT_MIRROR_REPO` for a shipped default.
- `scripts/publier_miroir_pocket_tts.py`, which copies the weights unmodified and writes the model card carrying the attribution, the licence, and Kyutai's acceptable-use policy.
- Attribution shown in the app under the cloning terms, as CC-BY-4.0 requires: author, licence, and a link to the original model.

### Notes

- Accepting Kyutai's own gate from inside the application is not possible: Hugging Face exposes no API for it. The mirror is what removes the detour.
- Removing the gate also removes where its acceptable-use policy was shown, so those commitments are carried by SoundMaster's own consent screen, which already required explicit consent of the person being cloned and prohibited deceptive use.
- This is a reading of the licence terms, not legal advice; the compliance page exists for a professional review before commercial distribution.

### Implementation

- The redirect uses the engine's documented `config=` argument: only `weights_path` is rewritten, since the tokenizer and the fallback weights already live in Kyutai's ungated repository. `language=` and `config=` are mutually exclusive, so the mirror replaces the language rather than adding to it.
- Any mirror failure — invalid identifier, unknown language, unreadable file — falls back to the normal path, so a broken mirror can never make cloning unavailable.

### Validation

- 102 automated tests passed; ruff and compilation clean.
- The rewrite was checked against the real installed configs for three languages, and a full generation was produced through the `config=` path, confirming the mechanism end to end (timbre 0.972 against the reference).

## 0.5.2 — 2026-08-09

Validated by installing the runtime and cloning a real voice end to end, rather than from the documentation. Three of the four findings below only appear when the model actually runs.

### Fixed

- `French` mapped to a bundle that does not exist. The runtime states plainly: "For technical reasons, only a larger 24-layer model is available for French." Every French generation therefore failed. The language table now mirrors what the runtime publishes instead of assuming a naming pattern, and a test asserts every mapped bundle exists in the installed `pocket_tts` config directory.
- `Auto` passed no language, and the resulting runtime cannot clone at all — it falls back to a build limited to its own voice catalogue. `Auto` now resolves to a real bundle, and new voices default to French rather than silently cloning with the English model.
- Ticking "Génération accélérée" on a machine with a GPU made generation *slower* (21.8 s instead of 8.8 s): quantised weights have no CUDA kernels, so the model was forced back onto the CPU. Quantisation is now only applied when there is no GPU.

### Added

- Automatic GPU placement for Pocket TTS. Upstream reports no GPU benefit, but that is the 6-layer English model; measured here on the 24-layer French bundle, CUDA is the fastest option (CPU 11.5 s, CPU+quantisation 9.6 s, CUDA 8.8 s for ~8 s of speech).
- Clear instructions when the cloning weights are unreachable. They live in a gated Hugging Face repository, so a new user's first attempt fails with a raw `ValueError`; SoundMaster now explains how to accept the terms and log in.
- The high-quality toggle is disabled, with an explanation, for languages that publish no second variant (French, English).

### Validation

- 91 automated tests passed; ruff and compilation clean.
- Real end-to-end run: `pocket-tts` installed from the extra, a French reference clip produced with a Windows SAPI voice the model has never seen, then cloned through SoundMaster's own service.
- Full click-by-click journey through the real window: locked menu → terms → return → new voice → sample loaded and played → saved → "Tester la voix" → "Générer" → result played → added to favorites → appears on the dashboard → regenerated.
- Warm generation runs at roughly real time (3.5 s of speech in 3.6 s), with spectral similarity to the reference between 0.985 and 0.998.

## 0.5.1 — 2026-08-09

### Fixed

- Pocket TTS ignored the selected language. It publishes one bundle per language inside the same repository and picks it through `load_model(language=...)`, so every generation silently used the default English model. All six published languages — English, French, German, Italian, Portuguese, Spanish — are now reachable from the language selector.
- The advanced temperature setting never reached Pocket TTS either: it is a load-time argument (`temp`), not a generate-time one. Language, temperature and quantisation are now part of the engine identity, so changing any of them reloads the model instead of reusing a mismatched one.
- Removed a model-path argument probe that could never match: `load_model` takes no model directory, and its `config` parameter is a config file rather than a snapshot.

### Added

- **Modèle haute qualité** toggle, selecting the slower 24-layer bundle published for every non-English language.
- **Génération accélérée** toggle, enabling Pocket TTS quantisation for faster generation.
- Portuguese in the language selector, and French labels for the existing entries. The canonical engine token is what gets stored, so saved voices and the other engines are unaffected.
- A clearer error when a requested language bundle is unavailable in the installed runtime.

### Validation

- 88 automated tests passed, including bundle mapping, load-option assembly, and engine reload on a language change.
- Ruff and Python compilation passed.
- Language-to-bundle mapping verified through the running UI for every entry, with and without the high-quality variant.

## 0.5.0 — 2026-08-09

### Added

- Kyutai **Pocket TTS** as the default cloning engine: a ~100M-parameter model that runs on the CPU, needs no reference transcript, and skips the local Whisper pass entirely. Available through the new `pocket` extra and the `pocket-tts` model profile.
- Cloned voice states are cached per sample, so repeated generations from the same recording only pay the cloning cost once; re-recording the sample invalidates the cache.
- **Paramètres → Mises à jour**: checks the public GitHub releases, compares versions, downloads the asset matching the install mode, and launches the installer. An MSI is preferred over the Inno Setup EXE when both are published; portable installs get the ZIP revealed in Explorer; source checkouts are pointed at `git pull`.
- Preloaded players for shortcut-bound favorites, so a hotkey pressed mid-game does not pay the media-backend setup cost.

### Changed

- Hovering a sound card preloads it, and replaying the same sound reuses the loaded source. Measured through the app: first click ~161 ms, after hover ~11 ms, repeat ~17 ms.
- Recording a sample no longer plays it back automatically; it loads into the player and waits for ▶. The same applies to a finished generation. Only "Tester la voix" plays immediately, which is its purpose.
- The advanced transcript field is disabled and explained when Pocket TTS is selected, since that engine clones straight from the clip.

### Fixed

- The voice-cloning consent redirect now explains itself: a banner states why the settings opened, the checkbox row pulses, and accepting returns to the cloning page instead of expecting a second click on the menu. Withdrawing consent cancels that return.
- Windows paging-file exhaustion while loading a model (`os error 1455`) is reported as actionable guidance instead of a raw OS error, following the exception's cause chain.
- The update panel derived the install mode twice and could offer an asset that disagreed with its own message; it is resolved once per check and reset between checks.

### Validation

- 83 automated tests passed, including a local HTTP server exercising the updater's streaming, truncation, cancellation, and error mapping.
- Ruff and Python compilation passed.
- The updater was verified against the real public release feed: correct tag, asset choice per install mode, and a real HTTPS asset stream (correct Content-Length, clean cancellation, no partial file left behind).
- Playback latency measured in the running application before and after the change.
- Real-window rendering reviewed for the updates tab and the engine list.

## 0.4.0 — 2026-08-01

### Added

- Built-in audio player for the voice workspace: the recorded, captured, or imported sample is now playable — with a seek bar and elapsed/total time — and plays back automatically as soon as a recording ends.
- **Tester la voix** action that generates a short phrase and plays it immediately, so the cloned voice can be judged before committing to a full generation. Test runs are never written to the history or the favorites.
- **Résultat** card with its own player, plus "add to favorites" and "open folder" actions; double-clicking a history row replays it.
- User-facing voice-cloning terms in Settings, tickable and untickable at any time, stating explicitly that the publisher is not responsible for how the feature is used.
- Voice previews follow the headset output selected in the settings, never the virtual cable.

### Changed

- Rebuilt the cloning screen as three numbered steps (choose a voice, give it a sample, write/test/generate) inside a single scrollable page, replacing the split editor/details panes.
- Renamed the user-facing "setup" wording to "voix" throughout the cloning workflow.
- The "Clonage de voix" menu entry is greyed out and locked until the terms are accepted; clicking it redirects to those terms, and unticking them re-locks the feature and leaves the page immediately.
- Generation no longer requires a saved voice: a recorded sample and some text are enough, and saving is offered for reuse.
- Settings are split into "Clonage de voix", "Audio et système", and "Conformité éditeur" tabs.
- Advanced controls now also expose the managed sample path.

### Fixed

- Labels, checkboxes, and sliders inherited the global window background and punched opaque page-coloured holes into every card; they are transparent now.
- The locked-feature card clipped its second paragraph because a word-wrapped rich-text label reports a one-paragraph size hint.

### Validation

- 58 automated tests passed.
- Ruff and Python compilation passed.
- Offscreen PyQt6 UI smoke tests passed.
- Real-window rendering reviewed for the locked state, the terms, the three steps, the advanced panel, and the compact-width reflow.
- End-to-end run of the packaged entry point: lock, redirect, acceptance, unlock.
- Real WAV playback verified: duration detection, auto-play after recording, play/stop toggle, replay, and a seek bar that advances.

## 0.3.0 — 2026-08-01

### Added

- Responsive 2–4 column grids for Dashboard favorites and the embedded Myinstants catalog.
- Content-adaptive Dashboard spacing with recent-use items following the favorites grid.
- Direct Myinstants previews without creating download jobs or cache files; favorites still download locally for offline use and shortcuts.
- Tester/Stop playback control for local favorites, with automatic reset when playback ends or fails.
- Persistent local voice bank with managed samples, microphone and Windows output recording, per-voice generation controls, and adjustable editor proportions.
- Optional WASAPI loopback capture support through the `audio` extra.

### Validation

- 41 automated tests passed.
- Ruff and Python compilation passed.
- Offscreen PyQt6 UI smoke tests passed.

## 0.2.1 — 2026-08-01

### Fixed

- Made the transcript-free TTS regression test independent of the optional `soundfile` runtime so the Windows release workflow can validate the project before packaging.

## 0.2.0 — 2026-08-01

### Added

- French PyQt6 soundboard shell with dashboard, voice cloning, Myinstants explorer, global shortcuts, settings, and system tray support.
- Local Myinstants search, previews, rights confirmation, cached downloads, favorites, and multi-download progress.
- Local Qwen3-TTS and OmniVoice integration points with optional automatic Faster-Whisper transcription.
- NVIDIA CUDA setup script with aligned PyTorch/TorchAudio wheels and BF16/FP16 fallback handling.
- GPU/TTS diagnostics in Settings, including CUDA, VRAM, BF16, runtime, and model availability.
- Windows packaging workflow for an Inno Setup installer and portable ZIP, plus automatic GitHub Releases.
- Compliance settings, publisher/legal document references, privacy defaults, third-party notices, and release checks.
- Regression coverage for UI startup, Myinstants flows, library persistence, GPU diagnostics, voice workers, and transcript-free Qwen generation.

### Validation

- 33 automated tests passed.
- Ruff and Python compilation passed.
- Offscreen UI startup, navigation, and shutdown passed.
- Live Myinstants search and MP3 cache download passed.
- Qwen3-TTS GPU generation passed on an NVIDIA RTX 4050 Laptop GPU with CUDA 12.6 and BF16.

### Notes

- Release artifacts are unsigned; configure Authenticode signing before commercial distribution.
- Qwen3-TTS, OmniVoice, Faster-Whisper, Myinstants content, and user-provided audio remain subject to their own licenses, rights, and terms.
- SoX and `flash-attn` are optional performance/runtime improvements and are not required by the validated Qwen generation path.
