"""Tests for media helpers (video → audio extraction for voice cloning)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from soundmaster.core.media import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    VideoAudioExtractionError,
    extract_audio_from_video,
    is_video_file,
    sample_destination,
)


def test_common_audio_and_video_extensions_are_recognized() -> None:
    assert is_video_file(Path("clip.mp4"))
    assert is_video_file(Path("clip.MKV"))
    assert is_video_file(Path("capture.mov"))
    assert is_video_file(Path("clip.webm"))
    assert not is_video_file(Path("voice.wav"))
    assert not is_video_file(Path("voice.MP3"))
    assert not is_video_file(Path("clip.txt"))
    # The sets must never overlap: a file cannot be both.
    assert VIDEO_EXTENSIONS.isdisjoint(AUDIO_EXTENSIONS)
    # Core formats every user will try.
    for ext in ("mp4", "mkv", "mov", "webm", "avi"):
        assert ext in VIDEO_EXTENSIONS
    for ext in ("wav", "mp3", "flac", "ogg", "m4a"):
        assert ext in AUDIO_EXTENSIONS


def test_sample_destination_converts_videos_to_wav() -> None:
    managed = Path(r"D:\samples")
    assert sample_destination(Path("capture.mp4"), managed) == managed / "capture.wav"
    assert sample_destination(Path("voice.flac"), managed) == managed / "voice.flac"
    assert sample_destination(Path("voice.mp3"), managed) == managed / "voice.mp3"


def test_extract_audio_from_a_real_video(tmp_path: Path) -> None:
    """End-to-end: a generated MP4 is decoded to a playable 24 kHz mono WAV.

    PyAV is already a dependency (through faster-whisper); when it is missing
    the test is skipped rather than failing the whole suite.
    """

    av = pytest.importorskip("av")
    source = tmp_path / "sample.mp4"
    destination = tmp_path / "out.wav"
    sample_rate = 48_000
    duration = 1.0
    t = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False)
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    container = av.open(str(source), mode="w")
    stream = container.add_stream("aac", rate=sample_rate)
    stream.layout = "mono"
    frame = av.AudioFrame.from_ndarray(tone.reshape(1, -1), format="fltp", layout="mono")
    frame.sample_rate = sample_rate
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()

    result = extract_audio_from_video(source, destination)

    assert result == destination
    import soundfile as sf

    info = sf.info(str(destination))
    assert info.samplerate == 24_000
    assert info.channels == 1
    # AAC adds encoder padding (≈2× the signal for a 1 s clip) — only the
    # decoded signal length matters, not the exact container duration.
    assert info.duration >= duration - 0.15
    data, _ = sf.read(str(destination), dtype="float32")
    assert float(np.max(np.abs(data))) > 0.1  # audible tone, not silence


def test_extract_audio_reports_video_without_audio_track(tmp_path: Path) -> None:
    pytest.importorskip("av")
    av = pytest.importorskip("av")
    source = tmp_path / "silent.mp4"
    destination = tmp_path / "out.wav"
    # A video stream with no audio track at all.
    container = av.open(str(source), mode="w")
    stream = container.add_stream("mpeg4", rate=10)
    frame = av.VideoFrame(width=64, height=64, format="yuv420p")
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()

    with pytest.raises(VideoAudioExtractionError, match="aucune piste audio"):
        extract_audio_from_video(source, destination)


def test_extract_audio_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(VideoAudioExtractionError):
        extract_audio_from_video(tmp_path / "nope.mp4", tmp_path / "out.wav")
