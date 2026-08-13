"""Media handling helpers: extracting audio tracks from video files.

Voice cloning accepts an audio clip as its reference, but users naturally have
videos (screen recordings, phone captures, …). This module decodes the audio
track of a video into a WAV file with PyAV (FFmpeg libraries bundled in the
``av`` package, already a dependency of faster-whisper), so the rest of the app
never has to know whether the imported sample came from an audio or a video
file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Extensions whose audio track we can extract (lowercase, without dot).
VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        "mp4",
        "mkv",
        "mov",
        "avi",
        "webm",
        "m4v",
        "wmv",
        "flv",
        "mpg",
        "mpeg",
        "ts",
        "3gp",
        "ogv",
    }
)

AUDIO_EXTENSIONS: frozenset[str] = frozenset({"wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus"})


class VideoAudioExtractionError(RuntimeError):
    """Raised when the audio track of a video cannot be extracted."""


def is_video_file(path: Path) -> bool:
    """Whether ``path`` looks like a video file (by extension)."""
    return path.suffix.lower().lstrip(".") in VIDEO_EXTENSIONS


def _audio_filter(input_: Any) -> Any:
    """First audio stream of the container, or ``None``."""
    try:
        streams = list(input_.streams.audio)
    except (AttributeError, TypeError, ValueError):  # pragma: no cover - defensive
        return None
    return streams[0] if streams else None


def extract_audio_from_video(source: Path, destination: Path) -> Path:
    """Decode the audio track of ``source`` into a WAV file.

    The decoded audio is resampled to mono 24 kHz PCM — the sample rate the
    voice engines natively work at — so downstream consumers get a uniform
    format regardless of the source container. The destination is overwritten
    if it already exists.
    """

    try:
        import av
        import soundfile as sf
    except ImportError as error:
        raise VideoAudioExtractionError(
            "La lecture de vidéos nécessite le paquet av (fourni avec l’extra "
            "« voice-auto »). Installez-le puis réessayez."
        ) from error

    try:
        container = av.open(str(source))
        stream = _audio_filter(container)
        if stream is None:
            raise VideoAudioExtractionError(
                f"Cette vidéo ne contient aucune piste audio : {source.name}"
            )
        samples: list[Any] = []
        for frame in container.decode(stream):
            frame = frame.to_ndarray()
            samples.append(frame)
        if not samples:
            raise VideoAudioExtractionError(
                f"Impossible de lire la piste audio de : {source.name}"
            )
        import numpy as np

        audio = np.concatenate(samples, axis=1) if len(samples) > 1 else samples[0]
        if audio.ndim > 1:
            # Mix down to mono by averaging channels.
            audio = audio.mean(axis=0)
        destination.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(destination), audio, 24_000, subtype="PCM_16")
        return destination
    except VideoAudioExtractionError:
        raise
    except Exception as error:
        raise VideoAudioExtractionError(
            f"Impossible d’extraire l’audio de {source.name} : {error}"
        ) from error


def sample_destination(source: Path, managed_dir: Path) -> Path:
    """Return a collision-free WAV path in ``managed_dir`` for ``source``.

    Video files keep their stem and get the ``.wav`` extension; audio files
    keep their own extension so existing behavior is unchanged.
    """

    if is_video_file(source):
        return managed_dir / f"{source.stem}.wav"
    return managed_dir / source.name
