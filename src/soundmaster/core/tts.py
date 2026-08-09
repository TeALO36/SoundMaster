"""Optional local voice-cloning inference services.

The beginner flow never requires a manually typed transcript. Qwen3-TTS uses a
local Faster-Whisper pass when needed; OmniVoice can auto-transcribe its reference
clip through its own local ASR support. Heavy runtimes and model weights remain
lazy-loaded and are never imported at application startup.
"""

from __future__ import annotations

import gc
import inspect
from pathlib import Path
from threading import RLock
from typing import Any

from soundmaster.core.config import AppPaths
from soundmaster.core.models import get_profile, model_path

SUPPORTED_ENGINE_KEYS = ("pocket-tts", "qwen3-tts", "omnivoice")

# Pocket TTS ships one bundle per language inside the same repository and picks
# it through ``load_model(language=...)``. Every non-English language also has a
# slower 24-layer bundle that trades speed for quality.
POCKET_LANGUAGE_BUNDLES: dict[str, str] = {
    "English": "english",
    "French": "french",
    "German": "german",
    "Italian": "italian",
    "Portuguese": "portuguese",
    "Spanish": "spanish",
}
POCKET_HIGH_QUALITY_SUFFIX = "_24l"


def pocket_language_bundle(language: str, high_quality: bool = False) -> str | None:
    """Map a UI language to a Pocket TTS bundle name.

    ``None`` means "let the engine use its own default", which is what ``Auto``
    should do rather than forcing English on everyone.
    """

    bundle = POCKET_LANGUAGE_BUNDLES.get((language or "").strip())
    if bundle is None:
        return None
    # Only non-English bundles publish a 24-layer variant.
    if high_quality and bundle != "english":
        return f"{bundle}{POCKET_HIGH_QUALITY_SUFFIX}"
    return bundle

# Windows ERROR_COMMITMENT_LIMIT. Loading multi-gigabyte weights commits far more
# virtual memory than the default paging file allows on many gaming machines.
_WINDOWS_COMMITMENT_LIMIT = 1455
_MEMORY_ERROR_MARKERS = (
    "paging file",
    "fichier de pagination",
    "os error 1455",
    "1455",
)

OUT_OF_MEMORY_HINT = (
    "Windows a manqué de mémoire virtuelle pendant le chargement du modèle "
    "(erreur 1455 : fichier de pagination insuffisant).\n\n"
    "Essayez, dans cet ordre :\n"
    "• fermez les applications lourdes (jeux, navigateurs, Discord) puis réessayez ;\n"
    "• augmentez le fichier d’échange Windows : Paramètres système avancés → "
    "Performances → Avancé → Mémoire virtuelle → décochez la gestion automatique "
    "et fixez au moins 24576 Mo sur le disque du modèle ;\n"
    "• installez le modèle sur un disque disposant de plusieurs dizaines de Go libres ;\n"
    "• redémarrez Windows pour libérer la mémoire déjà réservée."
)


def _is_out_of_memory(error: BaseException) -> bool:
    """Detect the Windows paging-file failure behind an opaque loader error."""

    if isinstance(error, MemoryError):
        return True
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, MemoryError):
            return True
        if getattr(current, "winerror", None) == _WINDOWS_COMMITMENT_LIMIT:
            return True
        text = str(current).lower()
        if any(marker in text for marker in _MEMORY_ERROR_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


class VoiceGenerationError(RuntimeError):
    """Raised when local voice generation or automatic transcription fails."""


class QwenVoiceService:
    """Lazy process-local wrapper for the supported local cloning engines."""

    _POCKET_STATE_CACHE_SIZE = 4

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._model: Any = None
        self._model_path: Path | None = None
        self._engine_key: str | None = None
        self._whisper_model: Any = None
        self._pocket_states: dict[tuple[str, int, int], Any] = {}
        self._engine_options: dict[str, object] = {}
        self._generation_lock = RLock()

    def generate_clone(
        self,
        text: str,
        ref_audio: Path,
        ref_text: str = "",
        output_path: Path | None = None,
        language: str = "Auto",
        engine_key: str = "qwen3-tts",
        settings: dict[str, object] | None = None,
    ) -> Path:
        """Generate a local cloned voice WAV with the selected engine."""

        with self._generation_lock:
            return self._generate_clone(
                text, ref_audio, ref_text, output_path, language, engine_key, settings or {}
            )

    def _generate_clone(
        self,
        text: str,
        ref_audio: Path,
        ref_text: str,
        output_path: Path | None,
        language: str,
        engine_key: str,
        settings: dict[str, object],
    ) -> Path:
        text = text.strip()
        ref_text = ref_text.strip()
        if not text:
            raise VoiceGenerationError("Le texte à générer est vide.")
        if not ref_audio.is_file():
            raise VoiceGenerationError(f"Échantillon vocal introuvable : {ref_audio}")
        if output_path is None:
            raise VoiceGenerationError("Le chemin de sortie audio est manquant.")
        if engine_key not in SUPPORTED_ENGINE_KEYS:
            available = ", ".join(SUPPORTED_ENGINE_KEYS)
            raise VoiceGenerationError(
                f"Moteur vocal inconnu : {engine_key}. Disponibles : {available}."
            )

        profile = get_profile(engine_key)
        local_model = model_path(profile, self.paths)
        # Pocket TTS ships its own downloader and caches weights itself, so a
        # missing local snapshot is not an error for that engine.
        if engine_key != "pocket-tts" and (
            not local_model.is_dir() or not any(local_model.iterdir())
        ):
            raise VoiceGenerationError(
                f"Le modèle {profile.repository} n’est pas présent. "
                f"Lancez telecharger_modeles.bat {engine_key}."
            )

        # Pocket TTS takes its language, temperature and quantisation at load
        # time, so those belong to the engine identity, not to a generate call.
        load_options = (
            self._pocket_load_options(language, settings) if engine_key == "pocket-tts" else {}
        )
        model = self._load_engine(local_model, engine_key, load_options)
        try:
            if engine_key == "pocket-tts":
                audio, sample_rate = self._generate_pocket(model, text, ref_audio, settings)
            elif engine_key == "omnivoice":
                audio, sample_rate = (
                    self._generate_omnivoice(model, text, ref_audio, ref_text, settings)
                    if settings
                    else self._generate_omnivoice(model, text, ref_audio, ref_text)
                )
            else:
                if not ref_text:
                    ref_text = self._auto_transcribe(ref_audio, language)
                if not ref_text:
                    raise VoiceGenerationError(
                        "La transcription automatique n’a produit aucun texte. "
                        "Renseignez-la dans Réglages avancés."
                    )
                audio, sample_rate = (
                    self._generate_qwen(model, text, ref_audio, ref_text, language, settings)
                    if settings
                    else self._generate_qwen(model, text, ref_audio, ref_text, language)
                )

            import soundfile as sf

            output_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(output_path), audio, sample_rate)
        except VoiceGenerationError:
            raise
        except Exception as error:
            if _is_out_of_memory(error):
                self._release_engine()
                raise VoiceGenerationError(OUT_OF_MEMORY_HINT) from error
            raise VoiceGenerationError(
                f"Génération {profile.repository} impossible : {error}"
            ) from error
        return output_path

    @staticmethod
    def _pocket_load_options(
        language: str, settings: dict[str, object] | None
    ) -> dict[str, object]:
        """Collect the Pocket TTS arguments that are fixed at load time."""

        settings = settings or {}
        options: dict[str, object] = {}
        bundle = pocket_language_bundle(
            language, bool(settings.get("pocket_high_quality", False))
        )
        if bundle is not None:
            options["language"] = bundle
        temperature = settings.get("temperature")
        if isinstance(temperature, (int, float)):
            options["temp"] = float(temperature)
        if settings.get("pocket_quantize"):
            options["quantize"] = True
        return options

    def _generate_pocket(
        self,
        model: Any,
        text: str,
        ref_audio: Path,
        settings: dict[str, object] | None = None,
    ) -> tuple[Any, int]:
        """Generate with Kyutai Pocket TTS.

        No reference transcript and no Whisper pass are needed here, which is
        most of why this engine feels instant compared to the others.
        """

        state = self._pocket_voice_state(model, ref_audio)
        kwargs = self._supported_kwargs(model.generate_audio, settings or {})
        audio = model.generate_audio(state, text, **kwargs)
        return self._to_samples(audio), int(getattr(model, "sample_rate", 24_000))

    def _pocket_voice_state(self, model: Any, ref_audio: Path) -> Any:
        """Reuse a cloned voice state instead of re-encoding the sample.

        Cloning the reference clip dominates a Pocket TTS run, so repeated
        generations from the same sample should only pay for it once. The cache
        key follows the file's identity, so re-recording a sample invalidates it.
        """

        try:
            stat = ref_audio.stat()
            key = (str(ref_audio.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
        except OSError:
            key = (str(ref_audio), 0, 0)
        cached = self._pocket_states.get(key)
        if cached is not None:
            return cached
        state = model.get_state_for_audio_prompt(str(ref_audio))
        while len(self._pocket_states) >= self._POCKET_STATE_CACHE_SIZE:
            self._pocket_states.pop(next(iter(self._pocket_states)))
        self._pocket_states[key] = state
        return state

    @staticmethod
    def _supported_kwargs(function: Any, settings: dict[str, object]) -> dict[str, object]:
        """Forward advanced controls only when the installed build accepts them."""

        if not settings:
            return {}
        try:
            parameters = inspect.signature(function).parameters
        except (TypeError, ValueError):
            return {}
        if any(item.kind == inspect.Parameter.VAR_KEYWORD for item in parameters.values()):
            return dict(settings)
        return {key: value for key, value in settings.items() if key in parameters}

    @staticmethod
    def _to_samples(audio: Any) -> Any:
        """Return plain PCM samples from a torch tensor or an array-like."""

        for step in ("detach", "cpu", "numpy"):
            method = getattr(audio, step, None)
            if callable(method):
                audio = method()
        return audio

    @staticmethod
    def _generate_qwen(
        model: Any,
        text: str,
        ref_audio: Path,
        ref_text: str,
        language: str,
        settings: dict[str, object] | None = None,
    ) -> tuple[Any, int]:
        import torch

        with torch.inference_mode():
            kwargs: dict[str, object] = {
                "text": text,
                "language": language or "Auto",
                "ref_audio": str(ref_audio),
                "ref_text": ref_text,
            }
            kwargs.update(settings or {})
            wavs, sample_rate = QwenVoiceService._call_supported(
                model.generate_voice_clone, kwargs
            )
        return wavs[0], int(sample_rate)

    @staticmethod
    def _generate_omnivoice(
        model: Any,
        text: str,
        ref_audio: Path,
        ref_text: str,
        settings: dict[str, object] | None = None,
    ) -> tuple[Any, int]:
        import torch

        kwargs: dict[str, object] = {"text": text, "ref_audio": str(ref_audio)}
        if ref_text:
            kwargs["ref_text"] = ref_text
        kwargs.update(settings or {})
        with torch.inference_mode():
            audio = QwenVoiceService._call_supported(model.generate, kwargs)
        return audio[0], 24_000

    @staticmethod
    def _call_supported(function: Any, kwargs: dict[str, object]) -> Any:
        """Pass advanced controls only when the installed engine exposes them."""

        try:
            parameters = inspect.signature(function).parameters
        except (TypeError, ValueError):
            return function(**kwargs)
        if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
            return function(**kwargs)
        return function(**{key: value for key, value in kwargs.items() if key in parameters})

    def _auto_transcribe(self, ref_audio: Path, language: str) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise VoiceGenerationError(
                "La transcription automatique locale manque. Installez l’extra : "
                "python -m pip install 'soundmaster[voice-auto]'. "
                "Ou renseignez une transcription dans Réglages avancés."
            ) from error

        if self._whisper_model is None:
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            try:
                self._whisper_model = WhisperModel(
                    "small", device=device, compute_type=compute_type
                )
            except Exception as error:
                raise VoiceGenerationError(
                    f"Chargement de la transcription locale impossible : {error}"
                ) from error

        try:
            detected_language = None if not language or language == "Auto" else language[:2].lower()
            segments, _info = self._whisper_model.transcribe(
                str(ref_audio), language=detected_language, vad_filter=True
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as error:
            raise VoiceGenerationError(f"Transcription automatique impossible : {error}") from error

    def _load_engine(
        self,
        local_model: Path,
        engine_key: str,
        load_options: dict[str, object] | None = None,
    ) -> Any:
        load_options = load_options or {}
        if (
            self._model is not None
            and self._model_path == local_model
            and self._engine_key == engine_key
            # Language, temperature and quantisation are chosen when the engine
            # is built, so a change to any of them has to reload it.
            and self._engine_options == load_options
        ):
            return self._model
        self._release_engine()
        if engine_key == "pocket-tts":
            # Pocket TTS is CPU-first: its own report states GPU gives no gain at
            # batch size 1, so none of the CUDA/dtype selection below applies.
            self._model = self._load_pocket_engine(load_options)
            self._model_path = local_model
            self._engine_key = engine_key
            self._engine_options = dict(load_options)
            return self._model
        try:
            import torch
        except ImportError as error:
            raise VoiceGenerationError(
                "PyTorch manque. Installez l’extra : python -m pip install 'soundmaster[tts]'."
            ) from error

        cuda_available = torch.cuda.is_available()
        device_map = "cuda:0" if cuda_available else "cpu"
        if cuda_available:
            # Ada GPUs such as the RTX 4050 support BF16. Keep FP16 fallback for
            # older NVIDIA cards while preserving the CPU path.
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            torch.set_float32_matmul_precision("high")
        else:
            dtype = torch.float32
        try:
            if engine_key == "omnivoice":
                from omnivoice import OmniVoice

                self._model = OmniVoice.from_pretrained(
                    str(local_model), device_map=device_map, dtype=dtype
                )
            else:
                from qwen_tts import Qwen3TTSModel

                self._model = Qwen3TTSModel.from_pretrained(
                    str(local_model), device_map=device_map, dtype=dtype
                )
        except ImportError as error:
            package = "omnivoice" if engine_key == "omnivoice" else "qwen-tts"
            raise VoiceGenerationError(
                f"Le runtime {package} manque. Installez l’extra : "
                "python -m pip install 'soundmaster[tts]'."
            ) from error
        except Exception as error:
            self._release_engine()
            if _is_out_of_memory(error):
                raise VoiceGenerationError(OUT_OF_MEMORY_HINT) from error
            raise VoiceGenerationError(
                f"Chargement du modèle {engine_key} impossible : {error}"
            ) from error
        self._model_path = local_model
        self._engine_key = engine_key
        return self._model

    def _load_pocket_engine(self, load_options: dict[str, object]) -> Any:
        """Load Pocket TTS with the requested language bundle and options.

        Pocket TTS resolves and caches its own weights, so no model directory is
        passed here. Options are filtered against the installed signature so an
        older or newer build never fails on an argument it does not know.
        """

        try:
            from pocket_tts import TTSModel
        except ImportError as error:
            raise VoiceGenerationError(
                "Le runtime pocket-tts manque. Installez l’extra : "
                "python -m pip install 'soundmaster[pocket]'."
            ) from error
        loader = TTSModel.load_model
        kwargs = self._supported_kwargs(loader, load_options)
        try:
            return loader(**kwargs)
        except VoiceGenerationError:
            raise
        except Exception as error:
            if _is_out_of_memory(error):
                raise VoiceGenerationError(OUT_OF_MEMORY_HINT) from error
            language = kwargs.get("language")
            if language and self._mentions_language(error, str(language)):
                raise VoiceGenerationError(
                    f"La langue « {language} » n’est pas disponible pour Pocket TTS "
                    "dans cette version. Choisissez une autre langue dans les "
                    "réglages avancés, ou mettez à jour le runtime : "
                    "python -m pip install -U pocket-tts."
                ) from error
            raise VoiceGenerationError(
                f"Chargement de Pocket TTS impossible : {error}"
            ) from error

    @staticmethod
    def _mentions_language(error: BaseException, language: str) -> bool:
        text = str(error).lower()
        return language.lower() in text or "language" in text

    def _release_engine(self) -> None:
        self._pocket_states.clear()
        self._engine_options = {}
        old_model = self._model
        self._model = None
        self._model_path = None
        self._engine_key = None
        if old_model is not None:
            del old_model
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
