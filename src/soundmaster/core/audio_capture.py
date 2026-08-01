"""Optional Windows audio capture helpers for voice-reference recording."""

from __future__ import annotations

import wave
from pathlib import Path
from threading import Event
from typing import Any


def resolve_wasapi_output_device(sounddevice: Any, requested: int | str | None = None) -> int | str | None:
    """Resolve a UI output description to a sounddevice WASAPI output index."""

    if isinstance(requested, int):
        return requested
    devices = sounddevice.query_devices()
    hostapis = sounddevice.query_hostapis()
    wasapi_names = {
        index
        for index, hostapi in enumerate(hostapis)
        if "wasapi" in str(hostapi.get("name", "")).lower()
    }
    candidates = [
        (index, device)
        for index, device in enumerate(devices)
        if int(device.get("max_output_channels", 0)) > 0
        and (not wasapi_names or int(device.get("hostapi", -1)) in wasapi_names)
    ]
    if requested:
        requested_lower = requested.strip().lower()
        for index, device in candidates:
            if str(device.get("name", "")).strip().lower() == requested_lower:
                return index
        raise RuntimeError(f"Sortie audio introuvable : {requested}")
    if candidates:
        default_device = getattr(sounddevice, "default", None)
        default_pair = getattr(default_device, "device", None)
        default_output = default_pair[1] if isinstance(default_pair, (tuple, list)) else None
        for index, _device in candidates:
            if index == default_output:
                return index
        return candidates[0][0]
    return requested


class SystemAudioRecorder:
    """Capture a Windows output endpoint through WASAPI loopback when available."""

    def __init__(self, output_path: Path, device: int | str | None = None) -> None:
        self.output_path = output_path
        self.device = device
        self._stop_event = Event()
        self._stream: Any = None

    @staticmethod
    def available() -> bool:
        """Report whether the optional backend exposes the WASAPI loopback API."""

        try:
            import sounddevice as sd
        except ImportError:
            return False
        return all(
            hasattr(sd, attribute)
            for attribute in ("RawInputStream", "WasapiSettings", "query_devices")
        )

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as error:
            raise RuntimeError(
                "La capture de sortie nécessite l’extra audio : "
                "python -m pip install 'soundmaster[audio]'"
            ) from error

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        try:
            device = resolve_wasapi_output_device(sd, self.device)
            device_info = sd.query_devices(device)
            channels = min(2, max(1, int(device_info.get("max_output_channels", 2))))
            samplerate = int(device_info.get("default_samplerate", 48_000))
            extra_settings = sd.WasapiSettings(loopback=True)
            self._stream = sd.RawInputStream(
                device=device,
                channels=channels,
                samplerate=samplerate,
                dtype="int16",
                blocksize=1024,
                extra_settings=extra_settings,
            )
            self._stream.start()
            with wave.open(str(self.output_path), "wb") as output:
                output.setnchannels(channels)
                output.setsampwidth(2)
                output.setframerate(samplerate)
                while not self._stop_event.is_set():
                    data, _overflowed = self._stream.read(1024)
                    output.writeframes(data)
        except Exception as error:
            raise RuntimeError(
                f"Capture de la sortie Windows impossible : {error}"
            ) from error
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
