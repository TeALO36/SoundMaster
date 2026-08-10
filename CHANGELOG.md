# Changelog

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
