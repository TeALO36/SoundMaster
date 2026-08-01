import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from soundmaster.core.audio_capture import (
    SystemAudioRecorder,
    resolve_wasapi_output_device,
    wasapi_output_devices,
)


def _fake_sounddevice() -> SimpleNamespace:
    devices = [
        {"name": "Speakers", "hostapi": 0, "max_output_channels": 2, "default_samplerate": 48_000},
        {"name": "Microphone", "hostapi": 1, "max_output_channels": 0, "default_samplerate": 48_000},
    ]
    hostapis = [{"name": "Windows WASAPI"}, {"name": "MME"}]

    class FakeStream:
        last: "FakeStream | None" = None

        def __init__(self, **kwargs) -> None:
            self.callback = kwargs["callback"]
            self.closed = False
            self.stopped = False
            FakeStream.last = self

        def start(self) -> None:
            self.callback(b"\x00" * 4096, 1024, None, None)

        def stop(self) -> None:
            self.stopped = True

        def close(self) -> None:
            self.closed = True

    def query_devices(device=None):
        if device is None:
            return devices
        return devices[device]

    return SimpleNamespace(
        RawInputStream=FakeStream,
        WasapiSettings=lambda **kwargs: kwargs,
        query_devices=query_devices,
        query_hostapis=lambda: hostapis,
        default=SimpleNamespace(device=(1, 0)),
        FakeStream=FakeStream,
    )


def test_capability_error_is_clear_when_backend_is_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    message = SystemAudioRecorder.capability_error()
    assert message is not None
    assert "sounddevice" in message


def test_resolve_wasapi_output_prefers_default_device() -> None:
    sounddevice = _fake_sounddevice()

    assert resolve_wasapi_output_device(sounddevice) == 0
    assert resolve_wasapi_output_device(sounddevice, "Speakers") == 0
    assert wasapi_output_devices(sounddevice) == [("Speakers", 0)]


def test_resolve_wasapi_output_rejects_non_wasapi_device() -> None:
    sounddevice = _fake_sounddevice()

    try:
        resolve_wasapi_output_device(sounddevice, 1)
    except RuntimeError as error:
        assert "WASAPI" in str(error)
    else:
        raise AssertionError("A non-WASAPI device should be rejected")


def test_system_recorder_writes_and_closes_wav(monkeypatch, tmp_path: Path) -> None:
    sounddevice = _fake_sounddevice()
    monkeypatch.setitem(sys.modules, "sounddevice", sounddevice)
    output_path = tmp_path / "capture.wav"
    recorder = SystemAudioRecorder(output_path)
    worker = threading.Thread(target=recorder.start)
    worker.start()
    deadline = time.time() + 2
    while sounddevice.FakeStream.last is None and time.time() < deadline:
        time.sleep(0.01)
    recorder.stop()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert sounddevice.FakeStream.last is not None
    assert sounddevice.FakeStream.last.closed is True
    with wave.open(str(output_path), "rb") as captured:
        assert captured.getnchannels() == 2
        assert captured.getframerate() == 48_000
        assert captured.getnframes() > 0
