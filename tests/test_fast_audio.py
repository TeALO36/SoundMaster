"""Tests for the zero-latency playback engine (FastAudioEngine)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def fake_sounddevice(monkeypatch) -> None:
    """Provide a sounddevice stub so the module can construct streams."""

    class FakeStream:
        def __init__(self, *args, **kwargs):
            self._active = True

        def start(self) -> None:
            self._active = True

        def stop(self) -> None:
            self._active = False

        def close(self) -> None:
            self._active = False

        @property
        def active(self) -> bool:
            return self._active

    class FakeSD:
        def __init__(self):
            self.fail_start = False

        def OutputStream(self, *args, **kwargs) -> FakeStream:
            if self.fail_start:
                raise RuntimeError("device gone")
            return FakeStream()

        def query_devices(self):
            return []

    class FakeSF:
        @staticmethod
        def read(path, dtype="float32"):
            import wave

            with wave.open(str(path), "rb") as wav:
                sr = wav.getframerate()
                raw = wav.readframes(wav.getnframes())
            data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            return data, sr

    fake = FakeSD()
    monkeypatch.setattr("soundmaster.core.fast_audio.sd", fake)
    monkeypatch.setattr("soundmaster.core.fast_audio.SOUNDDEVICE_AVAILABLE", True)
    monkeypatch.setattr("soundmaster.core.fast_audio.sf", FakeSF)
    return fake


def test_continuous_output_reports_failure_when_no_stream(fake_sounddevice) -> None:
    from soundmaster.core.fast_audio import ContinuousAudioOutput

    output = ContinuousAudioOutput()
    # Queue a buffer on a live stream, then make every restart fail to
    # simulate a device that disappeared: play() must report failure instead
    # of queuing audio that would never be heard.
    pcm = np.zeros((4096, 2), dtype=np.float32)
    assert output.play(pcm) is True
    assert output.is_active() is True

    fake_sounddevice.fail_start = True
    output._stream = None
    assert output.is_active() is False
    assert output.play(pcm) is False
    output.close()


def test_fast_audio_engine_set_devices_repoints_both_outputs(fake_sounddevice) -> None:
    from soundmaster.core.fast_audio import FastAudioEngine

    engine = FastAudioEngine()
    original_headset = engine.headset_output._stream
    original_virtual = engine.virtual_output._stream

    engine.set_devices("Casque A", "Câble virtuel B")

    assert engine.headset_output._stream is not original_headset
    assert engine.virtual_output._stream is not original_virtual
    engine.close()


def test_stream_self_heals_in_background(fake_sounddevice, monkeypatch) -> None:
    """A dead stream is re-opened off-thread so the next click finds it warm."""

    import time

    from soundmaster.core.fast_audio import ContinuousAudioOutput

    # Spin the retry loop fast instead of waiting 1 s per attempt.
    monkeypatch.setattr("soundmaster.core.fast_audio.time.sleep", lambda _seconds: None)

    output = ContinuousAudioOutput()
    output._stream.stop()
    output._stream = None
    output._retry_pending = False
    fake_sounddevice.fail_start = True  # the device is temporarily gone

    # The click must fail fast (returning False for the QMediaPlayer fallback)
    # and hand the re-open to the background loop instead of freezing the UI.
    assert output.play(np.zeros((512, 2), dtype=np.float32)) is False
    assert output._retry_pending is True

    # The device comes back: the background loop re-opens the stream.
    fake_sounddevice.fail_start = False
    deadline = time.monotonic() + 5
    while output._retry_pending and time.monotonic() < deadline:
        time.sleep(0.01)

    assert output._retry_pending is False
    assert output.is_active() is True
    assert output.play(np.zeros((512, 2), dtype=np.float32)) is True
    output.close()


def test_fast_audio_engine_play_falls_back_when_stream_is_dead(fake_sounddevice, tmp_path: Path) -> None:
    from soundmaster.core.fast_audio import FastAudioEngine

    audio = tmp_path / "tone.wav"
    # A tiny 16-bit PCM WAV so soundfile can decode it without extra deps.
    sr = 8000
    samples = (np.sin(np.linspace(0, 2 * np.pi * 440, sr // 4)) * 32767).astype("<i2")
    import wave

    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(samples.tobytes())

    engine = FastAudioEngine()
    # Kill the virtual stream and make every restart fail: play() must report
    # failure so the caller falls back to QMediaPlayer instead of queueing
    # audio that would never be heard. The live headset stream is unaffected.
    engine.virtual_output._stream.stop()
    fake_sounddevice.fail_start = True

    assert engine.play(audio, virtual=True) is False
    assert engine.play(audio, virtual=False) is True
    # Closing the engine must stop the background retry loop, or its daemon
    # thread would outlive this test and touch module state for the rest of
    # the session.
    engine.close()
