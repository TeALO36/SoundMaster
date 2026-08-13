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


def _make_video(path, rate: int, layout: str):
    """Encode an MP4 whose audio track is a 440 Hz tone at ``rate``."""

    from fractions import Fraction

    import av
    import numpy as np

    channels = 2 if layout == "stereo" else 1
    container = av.open(str(path), mode="w")
    stream = container.add_stream("aac", rate=rate)
    stream.layout = layout
    total, block, written = int(rate * 2.0), 1024, 0
    while written < total:
        count = min(block, total - written)
        t = (np.arange(written, written + count) / rate).astype(np.float32)
        tone = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        planes = np.stack([tone] * channels) if channels > 1 else tone[None, :]
        frame = av.AudioFrame.from_ndarray(
            np.ascontiguousarray(planes), format="fltp", layout=layout
        )
        frame.rate, frame.pts, frame.time_base = rate, written, Fraction(1, rate)
        for packet in stream.encode(frame):
            container.mux(packet)
        written += count
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()
    return path


@pytest.mark.parametrize(
    ("rate", "layout"),
    [(48_000, "stereo"), (44_100, "stereo"), (24_000, "mono"), (16_000, "mono")],
)
def test_extraction_preserves_duration_and_pitch(tmp_path, rate: int, layout: str) -> None:
    """Regression: the audio was never resampled, only relabelled.

    A 48 kHz video — every phone and screen recording — came out twice as long
    and an octave too low because the samples were written unchanged under a
    24 kHz header.
    """

    pytest.importorskip("av")
    import wave

    import numpy as np

    from soundmaster.core.media import TARGET_SAMPLE_RATE, extract_audio_from_video

    source = _make_video(tmp_path / f"in_{rate}_{layout}.mp4", rate, layout)
    output = extract_audio_from_video(source, tmp_path / "out.wav")

    with wave.open(str(output), "rb") as handle:
        assert handle.getframerate() == TARGET_SAMPLE_RATE
        assert handle.getnchannels() == 1
        data = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16)

    duration = data.size / TARGET_SAMPLE_RATE
    assert abs(duration - 2.0) < 0.25, f"durée {duration:.2f}s au lieu de 2.0s"

    size = 1 << int(np.log2(data.size))
    spectrum = np.abs(np.fft.rfft(data[:size].astype(np.float64) * np.hanning(size)))
    dominant = np.fft.rfftfreq(size, 1 / TARGET_SAMPLE_RATE)[int(np.argmax(spectrum))]
    assert abs(dominant - 440.0) < 25, f"ton {dominant:.0f} Hz au lieu de 440 Hz"
