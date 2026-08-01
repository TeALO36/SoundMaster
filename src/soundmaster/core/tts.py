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

SUPPORTED_ENGINE_KEYS = ("qwen3-tts", "omnivoice")


class VoiceGenerationError(RuntimeError):
    """Raised when local voice generation or automatic transcription fails."""


class QwenVoiceService:
    """Lazy process-local wrapper for the supported local cloning engines."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._model: Any = None
        self._model_path: Path | None = None
        self._engine_key: str | None = None
        self._whisper_model: Any = None
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
        if not local_model.is_dir() or not any(local_model.iterdir()):
            raise VoiceGenerationError(
                f"Le modèle {profile.repository} n’est pas présent. "
                f"Lancez telecharger_modeles.bat {engine_key}."
            )

        model = self._load_engine(local_model, engine_key)
        try:
            if engine_key == "omnivoice":
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
            raise VoiceGenerationError(
                f"Génération {profile.repository} impossible : {error}"
            ) from error
        return output_path

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

    def _load_engine(self, local_model: Path, engine_key: str) -> Any:
        if (
            self._model is not None
            and self._model_path == local_model
            and self._engine_key == engine_key
        ):
            return self._model
        self._release_engine()
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
            raise VoiceGenerationError(
                f"Chargement du modèle {engine_key} impossible : {error}"
            ) from error
        self._model_path = local_model
        self._engine_key = engine_key
        return self._model

    def _release_engine(self) -> None:
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
