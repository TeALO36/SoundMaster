# Changelog

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
